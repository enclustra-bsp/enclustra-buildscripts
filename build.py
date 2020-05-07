#! /usr/bin/env python
# -*- coding: utf-8 -*-

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

# \file build.py
# \brief Enclustra Build Environment main file
# \author Karol Gugala <kgugala@antmicro.com>
# \date 2015-07-03
#
# \copyright Copyright (c) 2015-2017 Enclustra GmbH, Switzerland. All rights reserved.
# \licence This code is released under the Modified BSD licence.

# Check project dependencies
try:
    # At first try to import only the utils module
    # with all its dependencies. If it succeeds, a
    # pretty error message will be printed instead
    # of a raw one
    import sys
    import utils

    # initialize utils object
    utils = utils.Utils()

except ImportError as e:
    # could not import utils module, exit
    print("Dependencies missing: " + str(e))
    sys.exit(1)

try:
    # import the remaining modules with pretty
    # print message in case of the exception
    import os
    import configparser
    import subprocess
    import argparse
    import time
    import datetime
    import re
    from stat import S_ISREG, ST_MTIME, ST_MODE

    import target
    import glob
    import gui

except ImportError as e:
    # could not import one of the remaining
    # modules
    utils.print_message(utils.logtype.ERROR,
                        "Dependencies missing:",
                        e)
    # call exit explicitly in case the break
    # on error options is not set
    sys.exit(1)


registered_toolchains = dict()

master_repo_name = "sources"
bscripts_path = os.path.abspath(os.path.dirname(sys.argv[0]))
root_path = os.path.abspath(bscripts_path + "/..")
master_repo_path = root_path + "/" + master_repo_name
state = "INIT"
init_state = "INIT"
done = False
build_log_file = None
tool_name = "Enclustra Build Environment"
def_fname = None
project_file = None
project_mode_save = False

required_tools = (["make",        "--version", 3, "3.79.1"],
                  ["git",         "--version", 3, "1.7.8"],
                  ["tar",         "--version", 4, "1.15"],
                  ["unzip",       "-v",        2, "6.0"],
                  ["curl",        "--version", 2, "7.9.3"],
                  ["wget",        "--version", 3, "1.15"],
                  ["bc",          "--version", 2, "1.06.95"],
                  ["gcc",         "--version", 3, "4.8.3"],
                  ["g++",         "--version", 3, "4.8.3"],
                  ["patch",       "--version", 3, "2.7.1"],
                  ["flex",        "--version", 2, "2.5.35"],
                  ["bison",       "--version", 4, "3.0.2"],
                  ["cpio",        "--version", 4, "2.11"],
                  ["autoconf",    "--version", 4, "2.69"],
                  ["rsync",       "--version", 3, "3.1.0"])

# setup sigint handler
utils.init_sigint_handler()

# setup argument parser
parser = argparse.ArgumentParser(description=tool_name, prog='tool',
                                 formatter_class=lambda prog:
                                 argparse.HelpFormatter(
                                     prog,
                                     max_help_position=32))

parser.add_argument("--release", action='store',
                    required=False, dest='bs_release', metavar='ver',
                    help='specify release version of the buidscripts')

parser.add_argument("-L", "--list-devices", action='store_true',
                    required=False, dest='list_devices',
                    help='list all available devices')

parser.add_argument("--list-devices-raw", action='store_true',
                    required=False, dest='list_devices_raw',
                    help='list all available devices in a script friendly way')

parser.add_argument("-d", "--device", action='store', required=False,
                    dest='device', metavar='device',
                    help='specify device as follows: \
                       <family>/<module>/<base_board>/<boot_device>')

parser.add_argument("-l", "--list-targets", action='store_true',
                    required=False, dest='list_targets',
                    help='list all targets for chosen device')

parser.add_argument("--list-targets-raw", action='store_true', required=False,
                    dest='list_targets_raw',
                    help='list all targets for chosen device in a script'
                    ' friendly way')

parser.add_argument("-x",  action='append', required=False,
                    dest='target', metavar='target',
                    help='fetch and build specific target')

parser.add_argument("-f", "--fetch", action='append', required=False,
                    dest='target_fetch', metavar='target',
                    help='fetch specific target')

parser.add_argument("-b", "--build", action='append', required=False,
                    dest='target_build', metavar='target',
                    help='build specific target')

parser.add_argument("--custom-build", action='append', required=False, nargs=2,
                    dest='custom_target_build', metavar=('target', 'steps'),
                    help='build specific target with specific steps'
                    ' (comma separated)')

parser.add_argument("--fetch-history", action='append', required=False,
                    dest='fetch_history', metavar='target',
                    help='fetch specific target with history')

parser.add_argument("--list-dev-options", action='store_true', required=False,
                    dest='list_dev_options',
                    help='list all available device options for chosen device')

parser.add_argument("--list-dev-binaries", action='store_true', required=False,
                    dest='list_dev_binaries',
                    help='list all available binary files for chosen device')

parser.add_argument("-B", "--custom-binary", action='append', nargs=2,
                    dest='custom_copyfiles', type=str,
                    metavar=("file", "path"),
                    help='exchange selected binary file with the one'
                    ' pointed by the path')

parser.add_argument("--anti-unicorn", action='store_true',
                    required=False, dest='disable_colors',
                    help='disables colored output')

parser.add_argument("--expert-mode", action='store_true',
                    required=False, dest='expert_mode',
                    help='expert mode: prepare the environment for building'
                    ' the whole system manually')

parser.add_argument("-o", "--dev-option", action='store', required=False,
                    dest='device_option', metavar='index',
                    help='set device option by index, the default one will'
                    ' be used if not specified')

parser.add_argument("--generate-project", action='store_true', required=False,
                    dest='generate_project',
                    help='generate project directory instead of a regular output')

parser.add_argument("--build-project", action='store', required=False,
                    dest='build_project', metavar='project_file',
                    help='build project')

parser.add_argument("--build-project-auto", action='store', required=False,
                    dest='build_project_auto', metavar='project_file',
                    help='build project automatically, skip the gui')

parser.add_argument("-s", "--saved-config", action='store', required=False,
                    dest='saved_config', metavar='cfg',
                    help='use previously saved configuration file')

parser.add_argument("-c", "--clean-all", action='store_true',
                    required=False, dest='clean_all',
                    help='delete all downloaded code, binaries, tools and'
                    ' built files')

parser.add_argument("-C", "--clean-soft", action='store_true',
                    required=False, dest='clean_soft',
                    help='run clean commands for all specified targets'
                    ' (if available)')

parser.add_argument("-v", "--version", action='store_true', required=False,
                    dest='version',
                    help='print version')

# process main config
config = configparser.ConfigParser()
if config.read(root_path + "/enclustra.ini") is None:
    utils.print_message(utils.logtype.ERROR, "Configuration file not found!")
    sys.exit(1)
try:
    # get number of jobs to use in parallel builds
    nthreads_default = 9
    nthreads = config['general']['nthreads']
    # see if we should auto-determine it (use nproc + 1)
    if nthreads == "auto":
        try:
            import multiprocessing
            nthreads = multiprocessing.cpu_count() + 1
        except:
            nthreads = nthreads_default
            msg = "Couldn't get number of CPUs - using {} jobs"
            utils.print_message(utils.logtype.WARNING,
                                msg.format(nthreads))
    else:
        try:
            if int(nthreads) <= 0:
                raise ValueError
        except ValueError:
            nthreads = nthreads_default
            msg = "Invalid build jobs configuration - using {} jobs"
            utils.print_message(utils.logtype.WARNING,
                                msg.format(nthreads))

    history_path = config['general']['history_path']
    debug_calls = config.getboolean('debug', 'debug-calls')
    utils.set_debug_calls(debug_calls)
    quiet_mode = config.getboolean('debug', 'quiet-mode')
    utils.set_quiet_mode(quiet_mode)
    break_on_error = config.getboolean('debug', 'break-on-error')
    utils.set_break_on_error(break_on_error)
    if config.has_option('debug', 'build-logfile'):
        build_log = config['debug']['build-logfile']
        try:
            build_log_file = open(root_path + '/' + build_log, 'w')
        except Exception as ext:
            utils.print_message(utils.logtype.WARNING, "Could not open file",
                                build_log, "for writing. Error:", str(ext))
            build_log_file = None
        utils.set_log_file(build_log_file)

    for toolchain in config['toolchains']:
        utils.register_toolchain(registered_toolchains, toolchain, config,
                                 (config['toolchains'][toolchain] == "remote"))
except Exception as ext:
    utils.print_message(utils.logtype.ERROR, "Configuration file corrupted!",
                        str(ext))
    sys.exit(1)


args = parser.parse_args()

if args.disable_colors is True:
    utils.set_colors(False)

if args.generate_project:
    project_mode_save = True

# figure out release version
if args.bs_release:
    release = args.bs_release
    sys.argv.remove('--release')
    sys.argv.remove(args.bs_release)
else:
    release = 'master'

# add release to tool templates
utils.add_tool_template("ebe_release", release)
now = datetime.datetime.now()
revision = utils.get_git_revision(bscripts_path).rstrip('\n')
tool_version = tool_name + " (" + release + "-" + revision + ")\n"\
    "Running under Python version "\
    + str(sys.version.split()[0]) + "."\
    "\n\nCopyright (c) 2015-" + str(now.year) + \
    " Enclustra GmbH, Switzerland." \
    "\nAll rights reserved."


# define helper functions
def setup_output_dir(tgt, utl, odir):
    tgt.out_dir = odir
    utl.mkdir_p(odir)

    # add ebe overlays to tool templates
    try:
        ebe_overlays = odir + "/overlays"
        utl.add_tool_template("ebe_overlays", ebe_overlays)
        utl.mkdir_p(ebe_overlays)
    except Exception as e:
        msg = "Unable to create a directory for EBE overlays"
        utl.print_message(utl.logtype.ERROR, msg, str(e))


if args.version is True:
    print(str("\n" + tool_version + "\n"))
    sys.exit(0)

elif args.clean_all is True:
    utils.print_message(utils.logtype.INFO, "Cleaning ...")
    utils.remove_folder(root_path + "/bin")
    utils.remove_folder(root_path + "/binaries")
    call = "git submodule deinit --force sources"
    utils.call_tool(call)
    # get all the output dirs
    dirs = [name for name in os.listdir(root_path) if
            os.path.isdir(os.path.join(root_path, name))]
    out_dirs = filter(lambda pref: 'out_' in pref, dirs)
    for directory in out_dirs:
        utils.remove_folder(root_path + "/" + directory)
    utils.print_message(utils.logtype.INFO, "Done.")
    sys.exit(0)

# if we're in console mode
elif args.saved_config is not None:
    if not os.path.isfile(args.saved_config):
        utils.print_message(utils.logtype.ERROR,
                            "Specified configuration file does not exist:",
                            args.saved_config)
        sys.exit(1)

    def_fname = (args.saved_config.split("/")[-1]).split(".")[:-1][0]

    utils.print_message(utils.logtype.INFO,
                        "Using previously saved configuration file:",
                        args.saved_config)

    # initialize target
    t = target.Target(root_path, master_repo_path, "",
                      args.saved_config, "No name",
                      debug_calls, utils, history_path,
                      release, True)

    # binaries have to be set by hand
    if t.config.has_section("binaries") is True:
        for b in t.config["binaries"]:
            if t.config.getboolean("binaries", b):
                t.set_binaries(t.config[b]["description"])
                break

    # set the project name
    t.target_name = t.config["project"]["name"]
    # set config path
    t.config_path = root_path + t.config["project"]["path"]

    state = "DO_FETCH"

elif args.build_project is not None or args.build_project_auto is not None:

    if args.build_project is not None:
        project_file = os.path.abspath(args.build_project)
    else:
        project_file = os.path.abspath(args.build_project_auto)

    if not os.path.isfile(project_file):
        utils.print_message(utils.logtype.ERROR,
                            "Project file does not exist:",
                            project_file)
        sys.exit(1)

    def_fname = (project_file.split("/")[-1]).split(".")[:-1][0]

    utils.print_message(utils.logtype.INFO,
                        "Using project file:",
                        project_file)

    # initialize target
    t = target.Target(root_path,
                      os.path.dirname(project_file), "",
                      project_file, "No name",
                      debug_calls, utils,
                      os.path.dirname(project_file),
                      release, True)

    setup_output_dir(t, utils, os.path.dirname(project_file))

    # set the project name
    t.target_name = t.config["project"]["name"]

    if args.build_project is not None:
        state = "INIT"
    else:
        # build all targets
        for tgt in t.targets:
            t.targets[tgt]["build"] = True
        state = "DO_GET_TOOLCHAIN"

elif args.device is not None:
    # initialize target
    dev_path = root_path + "/targets/" + args.device
    parse_dir = root_path + "/targets"
    ini_files = list()
    if os.path.isfile(parse_dir + "/build.ini"):
        ini_files.append(parse_dir + "/build.ini")
    for directory in (str(args.device)).split("/"):
        parse_dir += "/" + directory
        if not os.path.exists(parse_dir):
            utils.print_message(utils.logtype.ERROR, "device argument "
                                "not supported: " + str(directory))
            sys.exit(1)
        if os.path.isfile(parse_dir + "/build.ini"):
            ini_files.append(parse_dir + "/build.ini")

    # check if user wants to list subdirs for the given device
    if args.list_devices:
        utils.list_devices(root_path, entry_point=args.device)
        sys.exit(0)
    elif args.list_devices_raw:
        utils.list_devices_raw(root_path, entry_point=args.device)
        sys.exit(0)

    # check if it is a bottom dir
    bottom = len([n for n in os.listdir(dev_path)
                 if os.path.isdir(os.path.join(dev_path, n))]) == 0

    # exit if not
    if not bottom:
        utils.print_message(utils.logtype.ERROR, "device argument "
                            "not complete: " + str(args.device))
        sys.exit(1)

    device_name = (str(args.device)).replace("/", "_").replace(" ", "_")
    t = target.Target(root_path, master_repo_path, dev_path, ini_files,
                      device_name, debug_calls, utils, history_path,
                      release, False)
    # if list only
    if args.list_targets is True:
        targets_list = t.get_build()
        print(str("Available targets for " + args.device + ":"))
        print(str("Default targets are marked with an [*]"))
        for tgt in targets_list:
            subs = []
            for st in t.get_subtargets(tgt[0]):
                subs.append(st.split(' ')[1])
            subs = ', '.join(subs)
            tgt[0] = tgt[0] + ' (' + subs + ')'
            if tgt[2] is True:
                tgt[0] = tgt[0] + " [*]"
            print(str(tgt[0]))
        sys.exit(0)
    elif args.list_targets_raw is True:
        targets_list = t.get_build()
        for tgt in targets_list:
            subs = []
            for st in t.get_subtargets(tgt[0]):
                subs.append(st.split(' ')[1])
            subs = ','.join(subs)
            tgt[0] = tgt[0] + ' ' + subs
            print(str(tgt[0]))
        sys.exit(0)

    if args.list_dev_options is True:
        binaries = t.get_marked_binaries()
        print(str("Available options for " + args.device + ":"))
        count = 1
        for binary in binaries:
            default = ""
            if binary["default"] is True:
                default = " (default)"
            print(str(count) + ". " + str(binary["description"]) + default)
            count += 1
        sys.exit(0)

    if args.list_dev_binaries is True:
        binaries = t.get_marked_binaries()
        print(str("Available binary files for " + args.device + ":"))
        for i, binary in enumerate(binaries):
            print("for set " + str(binary["description"])+":")
            for cf in binary["copyfiles"]:
                print("- "+cf[0])
        sys.exit(0)
    # divide targets into fetch/build groups
    fetch_group = []
    build_group = []
    build_opts = []

    if args.target is not None:
        fetch_group.extend(args.target)
        build_group.extend(args.target)

    if args.target_fetch is not None:
        fetch_group.extend(args.target_fetch)

    if args.target_build is not None:
        build_group.extend(args.target_build)

    if args.fetch_history is not None:
        fetch_group.extend(args.fetch_history)
        t.set_fetch_opts(args.fetch_history)

    if args.custom_target_build is not None:
        for tgt in args.custom_target_build:
            if len(tgt) > 1:
                for st in tgt[1].split(','):
                    build_opts.append(tgt[0] + " " + st)
            else:
                build_opts.extend(t.get_subtargets(tgt[0]))

            build_group.append(tgt[0])

    # Remove duplicates
    build_group = list(set(build_group))
    fetch_group = list(set(fetch_group))

    if args.clean_soft:
        clean_tar = fetch_group + build_group
        # remove duplicates
        clean_tar = list(set(clean_tar))
        if not clean_tar:
            clean_tar = t.targets.keys()
        t.clean_targets(clean_tar)
        sys.exit(0)

    if fetch_group or build_group:
        t.set_fetch(fetch_group)
        t.set_build(build_group)

        invalid_targets = t.validate_subtargets(build_opts)
        if len(build_opts) > 0:
            t.set_build_opts(build_opts)
        if len(invalid_targets) > 0:
            utils.print_message(utils.logtype.ERROR,
                                "Invalid targets specified:",
                                ', '.join(invalid_targets))
            sys.exit(1)
    else:
        t.set_active_targets()

    if args.device_option is not None:
        binaries = t.get_marked_binaries()
        index = int(args.device_option)
        if index < 1:
            utils.print_message(utils.logtype.ERROR,
                                "Invalid device option.")
            sys.exit(1)
        elif index > len(binaries):
            utils.print_message(utils.logtype.ERROR,
                                "Chosen option exceeds available option",
                                "count:", len(binaries))
            sys.exit(1)
        chosen_bin = binaries[index-1]
        t.set_binaries(chosen_bin["description"])
    else:
        # set the default one
        t.set_binaries(t.get_default_binary())

    # overwrite chosen binary set to use custom files
    if args.custom_copyfiles:
        for cf in args.custom_copyfiles:
            if os.path.isfile(str(cf[1])):
                if not t.set_binaries_copyfile(cf[0], cf[1]):
                    print("Setting binary component "+cf[0]+" failed.\n"
                          "Use --list-dev-binaries option to list valid"
                          " components")
                    sys.exit(1)
            else:
                print(cf[1] + " is not a valid path.")
                sys.exit(1)

    state = "DO_FETCH"
elif args.list_devices is True:
    utils.list_devices(root_path)
    sys.exit(0)
elif args.list_devices_raw:
    utils.list_devices_raw(root_path)
    sys.exit(0)
elif len(sys.argv) > 1:
    print(str("Specify the device to use the following arguments: " +
              " ".join(sys.argv[1:])) + "\n")
    utils.list_devices(root_path)
    sys.exit(1)
else:
    # if we're in gui mode add dialog to tools list
    required_tools += (["dialog", "--version", 2, "1.1-20120215"], )

# check tools
for tool in required_tools:
    if utils.check_tool(tool[0], tool[1], tool[2], tool[3]) is False:
        utils.print_message(utils.logtype.ERROR, "Version of", tool[0],
                            "has to be", tool[3], "or greater!")
        utils.print_message(utils.logtype.INFO, "For more information,"
                            " including list of required tools and packages,"
                            " refer to the user documentation.")
        sys.exit(1)

# Git before version 1.8.4 didn't support submodule shallow clone
git_use_depth = utils.check_tool("git", "--version", 3, "1.8.4")
# Git before version 1.8.1.6 didn't use the '--remote' switch in submodules
git_use_remote = utils.check_tool("git", "--version", 3, "1.8.1.6")

# create required folder
try:
    utils.mkdir_p(root_path + "/bin")
except Exception as ex:
    utils.print_message(utils.logtype.ERROR, "Unable to create 'bin' folder!",
                        ex)
    sys.exit(1)


# welcome msg
welcome_msg = tool_version
# if log file is set this will be logged
utils.print_message(utils.logtype.INFO, welcome_msg + "\n\n")

# Main loop
g = None
binary_path = ""
while done is False:
    used_previous_config = False
    if state == "INIT":
        g = gui.Gui(root_path+"/targets")
        g.show_welcome_screen(welcome_msg)

        history_path = os.path.expanduser("~") + "/.ebe/" + history_path + "/"

        if project_file:
            init_state = state = "BUILD_MENU"
        elif os.path.exists(history_path) and os.listdir(history_path):
            init_state = state = "HISTORY_MENU"
        else:
            init_state = state = "TARGET_MENU"

    if state == "HISTORY_MENU":
        cfg = []
        dirpath = history_path
        entries = (os.path.join(dirpath, fn) for fn in
                   glob.glob(dirpath+"*.ini"))
        entries = ((os.stat(path), path) for path in entries)
        entries = ((stat[ST_MTIME], path)
                   for stat, path in entries if S_ISREG(stat[ST_MODE]))

        for cdate, path in sorted(entries, reverse=True):
            path = path.split("/")[-1]
            cfg.append((path.split(".")[0], ""))

        code, tag = g.show_previous_configs(cfg)
        if code == "ok":
            if tag == g.new_config_tag:
                state = "TARGET_MENU"
            else:
                used_previous_config = True
                def_fname = tag
                dirpath = history_path
                # initialize target
                t = target.Target(root_path, master_repo_path, g.get_workdir(),
                                  dirpath + tag + ".ini", "No name",
                                  debug_calls, utils, history_path,
                                  release, used_previous_config)

                # binaries have to be set by hand
                if t.config.has_section("binaries") is True:
                    for b in t.config["binaries"]:
                        if t.config.getboolean("binaries", b):
                            t.set_binaries(t.config[b]["description"])
                            break

                # set the project name
                t.target_name = t.config["project"]["name"]
                # set config path
                t.config_path = root_path + t.config["project"]["path"]

                state = "SHOW_SUMMARY"
        else:
            subprocess.call("clear")
            sys.exit(0)

    if state == "TARGET_MENU":
        # show main menu
        code = "ok"
        while code == "ok":
            code = g.show_level_menu(init_state == "TARGET_MENU" and g.top)
            continue
        if code == "exit":
            subprocess.call("clear")
            sys.exit(0)
        elif code == "back":
            state = init_state
        elif code == "done":
            state = "FETCH_MENU"
            # initialize target
            t = target.Target(root_path, master_repo_path, g.get_workdir(),
                              g.get_inifiles(), g.get_target_name(),
                              debug_calls, utils, history_path, release,
                              used_previous_config)

    elif state == "FETCH_MENU":
        fetch_list = t.get_fetch()
        if fetch_list:
            code, tags = g.show_fetch_menu(fetch_list)
        else:
            state = "BUILD_MENU"

        if code in ("cancel", "esc"):
            state = "TARGET_MENU"
            g.step_out()
            continue
        elif code == "help":
            g.show_help(tags, t.get_target_helpbox(tags))
            continue
        else:
            if code == "ok":
                t.set_fetch(tags)
                state = "BUILD_MENU"
            elif code == "extra":
                t.set_fetch(tags)
                code, tags = g.show_fetch_opts_menu(t.get_fetch_opts())
                if code == "ok":
                    t.set_fetch_opts(tags)
            continue

    elif state == "BUILD_MENU":
        # prepare options for configs
        config_opts = t.get_build_opts("defconfig")
        for opt in config_opts:
            # modify option name
            target_name = opt[0].split(" ")[0]
            opt[0] = "Load initial " + target_name + " configuration"
            opt.append("Perform configuration step for " +
                       target_name + " target")

        code, tags = g.show_build_menu(t.get_build()+config_opts)
        if code == "ok":
            opt_tags = []
            # extract configuration tags
            for tag in list(tags):
                if "configuration" in tag:
                    opt_tags.append(tag.split(" ")[2]+" defconfig")
                    tags.remove(tag)
            t.set_build(tags)
            t.set_build_opts(opt_tags, "defconfig")
            # check configuration overwriting
            overwrite_string = t.get_config_overwrite(tags)
            if overwrite_string:
                code = g.dialog.yesno("Attention! Your current configuration \
                                for " + overwrite_string +
                                      " will be overwritten.",
                                      15, 60, yes_label="OK",
                                      no_label="Cancel")
                if code == "cancel":
                    continue
            if project_file is not None:
                state = "DO_GET_TOOLCHAIN"
            elif not t.fetch_only_run():
                state = "BINARIES_MENU"
            else:
                state = "SHOW_SUMMARY"
        elif code == "help":
            g.show_help(tags, t.get_target_helpbox(tags))
            continue
        elif code in ("cancel", "esc"):
            if project_file is not None:
                subprocess.call("clear")
                sys.exit(0)
            state = "FETCH_MENU"
        continue

    elif state == "BINARIES_MENU":
        binaries = t.get_binaries()
        # If there are no binaries skip to the next state
        if len(binaries) == 0:
            state = "SHOW_SUMMARY"
            continue

        code, tags = g.show_binaries_menu(binaries)
        if code == "ok":
            t.set_binaries(tags)
            state = "CUSTOM_FILES_MENU"
        elif code == "help":
            g.show_help(tags, t.get_binary_helpbox(tags))
            continue
        elif code in ("cancel", "esc"):
            state = "BUILD_MENU"
        continue

    elif state == "CUSTOM_FILES_MENU":
        code, tags = g.show_custom_files_menu(t.binaries, t.const_files)
        if code == "extra":  # Edit
            state = "BINARY_PATH_SEL"
        elif code == "ok":
            state = "SHOW_SUMMARY"
        elif code == "help":  # Default
            # reset all paths to default
            t.set_binaries_copyfile_default(tags)
        elif code in ("esc", "cancel"):  # Back
            state = "BINARIES_MENU"
        continue

    elif state == "BINARY_PATH_SEL":
        selected_file = tags
        initial_path = binary_path if binary_path else \
            t.get_binary_srcpath(selected_file)
        code, binary_path = g.show_custom_binary_sel(selected_file,
                                                     initial_path)
        if code == "ok":
            # check if selected file is valid
            if os.path.isfile(binary_path):
                # update copy file in binaries set
                # and return to custom files menu
                t.set_binaries_copyfile(selected_file, binary_path)
                binary_path = ""
                state = "CUSTOM_FILES_MENU"
            else:
                code = g.show_warning(binary_path+" is not a valid file.")
        elif code in ("cancel", "esc"):
            binary_path = ""
            state = "CUSTOM_FILES_MENU"
        continue

    elif state == "SHOW_SUMMARY":
        code = g.show_summary_menu(t.get_summary(), used_previous_config)
        if code == "ok":
            if used_previous_config is True:
                state = "DO_FETCH"
            else:
                state = "SAVE_CONFIG"
        elif code in ("cancel", "esc"):
            if used_previous_config is True:
                state = "FETCH_MENU"
            elif not t.fetch_only_run():
                state = "CUSTOM_FILES_MENU"
            else:
                state = "BUILD_MENU"
        continue

    elif state == "SAVE_CONFIG":
        if def_fname is None:
            def_fname = time.strftime("%Y%m%d%H%M%S_") + t.get_name()

        string = def_fname
        code = "?"

        while True:
            code, string = g.show_history_fname_dialog(string)
            if code == "extra":
                code = g.show_project_menu()
                if "enable" in code[1]:
                    project_mode_save = True
                continue
            if code != "ok":
                break
            if not re.match("^[a-zA-Z0-9_+-]+$", string):
                err_msg = \
                        "Please use the following character set [a-zA-Z0-9_+-]"
                g.dialog.msgbox(err_msg, width=len(err_msg)+10)
                continue
            break

        def_fname = string
        if code == "ok":
            # save config (in project mode config is saved as the last step)
            if not project_mode_save:
                t.save_config(def_fname)
        else:
            def_fname = t.get_name()

        state = "DO_FETCH"

    elif state == "DO_FETCH":
        # create out dir
        if def_fname is None:
            def_fname = t.get_name()
        setup_output_dir(t, utils,
                         os.path.abspath(root_path + "/out_" + def_fname))

        # clear console
        if g:
            subprocess.call("clear")
        t.do_fetch(git_use_depth, git_use_remote)
        state = "DO_GET_TOOLCHAIN"

    elif state == "DO_GET_TOOLCHAIN":
        if g and project_file:
            subprocess.call("clear")

        required_toolchains = t.get_required_toolchains()
        try:
            toolchains_paths = utils.acquire_toolchains(required_toolchains,
                                                        registered_toolchains,
                                                        root_path, debug_calls)
        except Exception as ex:
            utils.print_message(utils.logtype.ERROR,
                                "Failed to acquire toolchain, skipping build!",
                                str(ex))
            done = True
            continue

        if args.expert_mode is True:
            state = "EXPERT_MODE"
        else:
            state = "DO_BUILD"

    elif state == "EXPERT_MODE":
        utils.create_xpmode_script(root_path)
        utils.print_message(utils.logtype.INFO,
                            "To use Expert Mode run '. sources/xpmode_env.sh'")
        sys.exit(0)

    elif state == "DO_BUILD":
        t.do_build(toolchains_paths, nthreads)
        state = "HANDLE_BINARIES"

    elif state == "HANDLE_BINARIES":
        state = "DO_COPYFILES"
        if t.fetch_only_run():
            continue
        binaries_path = root_path + "/binaries"
        t.do_get_binaries(binaries_path)

    elif state == "DO_COPYFILES":
        utils.print_message(utils.logtype.INFO,
                            "Working directory: " + root_path)
        t.do_copyfiles()
        state = "DO_IMAGE_GEN"

    elif state == "DO_IMAGE_GEN":
        setup_output_dir(t, utils, root_path + "/out_" + def_fname)

        required_toolchains = t.get_required_toolchains()
        try:
            toolchains = utils.acquire_toolchains(required_toolchains,
                                                  registered_toolchains,
                                                  root_path, debug_calls)
        except Exception as ex:
            utils.print_message(utils.logtype.ERROR,
                                "Failed to acquire toolchain, skipping build!",
                                str(ex))
            done = True
            continue

        t.do_generate_image(t.out_dir, toolchains)
        if project_mode_save or (project_file is not None):
            state = "GENERATE_PROJECT"
        else:
            done = True

    elif state == "GENERATE_PROJECT":
        done = True

        # if we are building project, then only update the ini file
        if project_file is not None:
            t.resave_project(project_file)
            continue

        # elsewise, generate it from scratch
        copy_targets = [tar for tar in t.get_fetch() if tar[2]]
        for tar in copy_targets:
            src_dir = t.master_repo_path + "/" + \
                      t.targets[tar[0]]["repository"]
            tar_dir = t.out_dir + "/" + t.targets[tar[0]]["repository"]
            call = "git clone " + src_dir + " " + tar_dir
            utils.call_tool(call)
            call = "git remote remove origin"
            t.do_custom_cmd(toolchains, tar_dir, call)

        t.save_project(def_fname, t.out_dir)

if done:
    utils.print_message(utils.logtype.INFO, "-" * 80)
    if utils.get_error_count():
        utils.print_message(utils.logtype.ERROR, "BUILD FAILED")
    else:
        msg = "BUILD SUCCEEDED"
        msg_type = utils.logtype.INFO
        if utils.get_warning_count():
            msg += " with " + str(utils.get_warning_count())
            if utils.get_warning_count() == 1:
                msg += " warning"
            else:
                msg += " warnings"
            msg_type = utils.logtype.WARNING
        utils.print_message(msg_type, msg)

    for line in t.get_summary(oneline=True).split("\n"):
        utils.print_message(utils.logtype.INFO, line)

    if not t.fetch_only_run() and not utils.get_error_count():
        utils.print_message(utils.logtype.INFO, "Output directory: ./" +
                            os.path.relpath(t.out_dir))

if build_log_file is not None:
    build_log_file.close()

# non-zero exit code in case of errors
if utils.get_error_count():
    sys.exit(1)
