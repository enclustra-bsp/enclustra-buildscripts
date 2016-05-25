#! /usr/bin/env python2
# -*- coding: utf-8 -*-

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

# \file build.py
# \brief Enclustra Build Environment main file
# \author Karol Gugala <kgugala@antmicro.com>
# \date 2015-07-03
#
# \copyright Copyright (c) 2015 Enclustra GmbH, Switzerland. All rights reserved.
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
    import shutil
    import argparse
    import time
    import re
    from stat import S_ISREG, ST_MTIME, ST_MODE

    import target
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
root_path= os.path.abspath(bscripts_path + "/..")
master_repo_path = root_path + "/" + master_repo_name
state = "INIT"
done = False
build_log_file = None
tool_name = "Enclustra Build Environment"
def_fname = None

required_tools = (["make",   "--version", 3, "3.79.1"],
                  ["git",    "--version", 3, "1.7.8"],
                  ["tar",    "--version", 4, "1.15"],
                  ["curl",   "--version", 2, "7.9.3"],
                  ["gcc",    "--version", 3, "4.8.3"],
                  ["g++",    "--version", 3, "4.8.3"],
                  ["patch",  "--version", 3, "2.7.1"])

# setup sigint handler
utils.init_sigint_handler()

# setup argument parser
parser = argparse.ArgumentParser(description=tool_name, prog='tool',
                                 formatter_class=lambda prog:
                                 argparse.HelpFormatter(
                                     prog,
                                     max_help_position=32))

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
    manifest_repo = config['general']['manifest_repository']
    nthreads = config['general']['nthreads']
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


revision = utils.get_git_revision(bscripts_path).rstrip('\n')
tool_version = tool_name + " (v0.0-" + revision + ")\n"\
    "Running under Python version "\
    + str(sys.version.split()[0]) + "."\
    "\n\nCopyright (c) 2015 Enclustra GmbH, Switzerland." \
    "\nAll rights reserved."

args = parser.parse_args()

if args.disable_colors is True:
    utils.set_colors(False)

if args.version is True:
    print(str("\n" + tool_version + "\n"))
    sys.exit(0)

elif args.clean_all is True:
    utils.print_message(utils.logtype.INFO, "Cleaning ...")
    utils.remove_folder(root_path + "/bin")
    utils.remove_folder(root_path + "/binaries")
    utils.remove_folder(root_path + "/sources")
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
                      debug_calls, utils, history_path)

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
                      device_name, debug_calls, utils, history_path)
    # if list only
    if args.list_targets is True:
        targets_list = t.get_fetch()
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
        targets_list = t.get_fetch()
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
        t.clean_targets(clean_tar,
                        utils.acquire_toolchains(t.get_required_toolchains(),
                                                 registered_toolchains,
                                                 root_path, debug_calls))
        sys.exit(1)

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


# init master repository
utils.print_message(utils.logtype.INFO, "Initializing master repository")
pull = False
if os.path.isdir(master_repo_path) is True:
    if os.path.exists(master_repo_path+"/.git") is True:
        pull = True
    else:
        # remove sources dir
        shutil.rmtree(master_repo_path)

# if pull only
if pull is True:
    with utils.cd(master_repo_path):
        call = "git pull"
        sp = utils.call_tool(call)
# clone new
else:
    call = "git clone " + manifest_repo + " \"" + master_repo_path + "\""
    sp = utils.call_tool(call)
if sp != 0:
    utils.print_message(utils.logtype.ERROR,
                        "Fetching master repository failed!")
    sys.exit(1)

# welcome msg
welcome_msg = tool_version
# if log file is set this will be logged
utils.print_message(utils.logtype.INFO, welcome_msg + "\n\n")

# Main loop
g = None
while done is False:
    used_previous_config = False
    if state == "INIT":
        g = gui.Gui(root_path+"/targets")
        g.show_welcome_screen(welcome_msg)

        history_path = os.path.expanduser("~") + "/.ebe/" + history_path + "/"

        if os.path.exists(history_path) and os.listdir(history_path):
            state = "HISTORY_MENU"
        else:
            state = "TARGET_MENU"

    if state == "HISTORY_MENU":
        cfg = []
        dirpath = history_path
        entries = (os.path.join(dirpath, fn) for fn in os.listdir(dirpath))
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
                                  debug_calls, utils, history_path)

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
            code = g.show_level_menu()
            continue
        if code == "exit":
            subprocess.call("clear")
            sys.exit(0)
        elif code == "done":
            state = "FETCH_MENU"
            # initialize target
            t = target.Target(root_path, master_repo_path, g.get_workdir(),
                              g.get_inifiles(), g.get_target_name(),
                              debug_calls, utils, history_path)

    elif state == "FETCH_MENU":
        code, tags = g.show_fetch_menu(t.get_fetch())
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
        code, tags = g.show_build_menu(t.get_build())
        if code == "ok":
            t.set_build(tags)
            if not t.fetch_only_run():
                state = "BINARIES_MENU"
            else:
                state = "SHOW_SUMMARY"
        elif code == "help":
            g.show_help(tags, t.get_target_helpbox(tags))
            continue
        elif code == "extra":
            t.set_build(tags)
            code, subtags = g.show_build_opts_menu(t.get_build_opts())
            if code == "ok":
                t.set_build_opts(subtags)
                continue
        elif code in ("cancel", "esc"):
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
            state = "SHOW_SUMMARY"
        elif code == "help":
            g.show_help(tags, t.get_binary_helpbox(tags))
            continue
        elif code in ("cancel", "esc"):
            state = "BUILD_MENU"
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
                state = "BINARIES_MENU"
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
            if code != "ok":
                break
            if not re.match("^[a-zA-Z0-9_-]+$", string):
                err_msg = \
                        "Please use the following character set [a-zA-Z0-9_-]"
                g.dialog.msgbox(err_msg, width=len(err_msg)+10)
                continue
            break

        def_fname = string
        if code == "ok":
            # save config
            t.save_config(def_fname)
        else:
            def_fname = t.get_name()

        state = "DO_FETCH"

    elif state == "DO_FETCH":
        # clear console
        if g:
            subprocess.call("clear")
        t.do_fetch(git_use_depth, git_use_remote)
        state = "DO_GET_TOOLCHAIN"

    elif state == "DO_GET_TOOLCHAIN":
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
                "To enter Expert Mode run '. sources/xpmode_env.sh'")
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
        if def_fname is None:
            def_fname = t.get_name()
        utils.print_message(utils.logtype.INFO,
                            "Working directory: " + root_path)
        out_dir = root_path + "/out_" + def_fname
        out_dir = os.path.abspath(out_dir)
        utils.mkdir_p(out_dir)
        t.do_copyfiles(out_dir)
        state = "DO_IMAGE_GEN"

    elif state == "DO_IMAGE_GEN":
        out_dir = root_path + "/out_" + def_fname

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

        t.do_generate_image(out_dir, toolchains)
        done = True

if done:
    utils.print_message(utils.logtype.INFO, "-" * 80)
    if utils.get_error_count():
        utils.print_message(utils.logtype.ERROR, "BUILD FAILED")
    else:
        msg = "BUILD_SUCCEEDED"
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
                            os.path.relpath(out_dir))

if build_log_file is not None:
    build_log_file.close()
