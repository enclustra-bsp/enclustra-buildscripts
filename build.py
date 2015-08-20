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
    print "Dependencies missing: " + str(e)
    sys.exit(1)

try:
    # import the remaining modules with pretty
    # print message in case of the exception
    import os
    import configparser
    import subprocess
    import shutil
    import argparse

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
root_path = os.getcwd()
master_repo_path = root_path + "/" + master_repo_name
state = "INIT"
done = False
build_log_file = None
tool_name = "Enclustra Build Environment"

required_tools = (["make",   "--version", 3, "3.79.1"],
                  ["git",    "--version", 3, "1.7.8"],
                  ["tar",    "--version", 4, "1.15"],
                  ["wget",   "--version", 3, "1.0"],
                  ["gcc",    "--version", 3, "4.8.3"],
                  ["g++",    "--version", 3, "4.8.3"],
                  ["patch",  "--version", 3, "2.7.1"])

# setup sigint handler
utils.init_sigint_handler()

# setup argument parser
parser = argparse.ArgumentParser(description=tool_name, prog='tool',
                                 formatter_class=lambda prog:
                                 argparse.HelpFormatter(prog, max_help_position=32))

parser.add_argument("-L", "--list-devices", action='store_true',
                    required=False, dest='list_devices',
                    help='list all available devices')

parser.add_argument("-d", "--device", action='store', required=False,
                    dest='device', metavar='device',
                    help='specify device as follows: \
                       <family>/<module>/<base_board>/<boot_device>')

parser.add_argument("-l", "--list-targets", action='store_true', required=False,
                    dest='list_targets',
                    help='list all targets for chosen device')

parser.add_argument("-x",  action='append', required=False,
                    dest='target', metavar='target',
                    help='fetch and build specific target')

parser.add_argument("-f", "--fetch", action='append', required=False,
                    dest='target_fetch', metavar='target',
                    help='fetch specific target')

parser.add_argument("-b", "--build", action='append', required=False,
                    dest='target_build', metavar='target',
                    help='build specific target')

parser.add_argument("--fetch-history", action='append', required=False,
                    dest='fetch_history', metavar='target',
                    help='fetch specific target with history')

parser.add_argument("--list-dev-options", action='store_true', required=False,
                    dest='list_dev_options',
                    help='list all available device options for chosen device')

parser.add_argument("-o", "--dev-option", action='store', required=False,
                    dest='device_option', metavar='index',
                    help='set device option by index, the default one will'
                    ' be used if not specified')

parser.add_argument("-c", "--clean-all", action='store_true',
                    required=False, dest='clean_all',
                    help='delete all downloaded code, binaries, tools and'
                    ' built files')

parser.add_argument("-v", "--version", action='store_true', required=False,
                    dest='version',
                    help='print version')

# process main config
config = configparser.ConfigParser()
if config.read("enclustra.ini") is None:
    utils.print_message(utils.logtype.ERROR, "Configuration file not found!")
    sys.exit(1)
try:
    manifest_repo = config['general']['manifest_repository']
    nthreads = config['general']['nthreads']
    debug_calls = config.getboolean('debug', 'debug-calls')
    utils.set_debug_calls(debug_calls)
    quiet_mode = config.getboolean('debug', 'quiet-mode')
    utils.set_quiet_mode(quiet_mode)
    break_on_error = config.getboolean('debug', 'break-on-error')
    utils.set_break_on_error(break_on_error)
    if config.has_option('debug', 'build-logfile'):
        build_log = config['debug']['build-logfile']
        try:
            build_log_file = open(build_log, 'w')
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


revision = utils.get_git_revision().rstrip('\n')
tool_version = tool_name + " (v0.0-" + revision + " (beta))\n"\
    "Running under Python version "\
    + str(sys.version.split()[0]) + "."\
    "\n\nCopyright (c) 2015 Enclustra GmbH, Switzerland." \
    "\nAll rights reserved."

args = parser.parse_args()

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
elif args.device is not None:
    # initialize target
    dev_path = root_path + "/targets/" + args.device
    parse_dir = root_path + "/targets"
    ini_files = list()
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
        utils.list_devices(entry_point=args.device)
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
    t = target.Target(master_repo_path, dev_path, ini_files,
                      device_name, debug_calls, utils)
    # if list only
    if args.list_targets is True:
        targets_list = t.get_fetch()
        print(str("Available targets for " + args.device + ":"))
        print(str("Default targets are marked with an (*)"))
        for tgt in targets_list:
                if tgt[2] is True:
                    tgt[0] = tgt[0] + " (*)"
                print(str(tgt[0]))
        sys.exit(0)

    if args.list_dev_options is True:
        binaries = t.get_binaries()
        print(str("Available options for " + args.device + ":"))
        count = 1
        for binary in binaries:
            default = ""
            if binary[2] is True:
                default = " (default)"
            print(str(count) + ". " + str(binary[0]) + default)
            count += 1
        sys.exit(0)

    # divide targets into fetch/build groups
    fetch_group = []
    build_group = []

    if args.target is not None:
        fetch_group.extend(args.target)
        build_group.extend(args.target)

    if args.target_fetch is not None:
        fetch_group.extend(args.target_fetch)

    if args.target_build is not None:
        build_group.extend(args.target_build)

    if fetch_group or build_group:
        t.set_fetch(fetch_group)
        t.set_build(build_group)
    # else: build all default targets

    if args.fetch_history is not None:
        t.set_fetch_opts(args.fetch_history)

    if args.device_option is not None:
        binaries = t.get_binaries()
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
        t.set_binaries(chosen_bin[0])
    else:
        # set the default one
        binaries = t.get_binaries()
        for binary in binaries:
            if binary[2] is True:
                t.set_binaries(binary[0])
                break

    state = "DO_FETCH"
elif args.list_devices is True:
    utils.list_devices()
    sys.exit(0)
elif len(sys.argv) > 1:
    print(str("Specify the device to use the following arguments: " +
              " ".join(sys.argv[1:])) + "\n")
    utils.list_devices()
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
    call = "git clone " + manifest_repo + " " + master_repo_name
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
    if state == "INIT":
        g = gui.Gui(root_path+"/targets")
        g.show_welcome_screen(welcome_msg)
        state = "TARGET_MENU"

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
            t = target.Target(master_repo_path, g.get_workdir(),
                              g.get_inifiles(), g.get_target_name(),
                              debug_calls, utils)

    elif state == "FETCH_MENU":
        code, tags = g.show_fetch_menu(t.get_fetch())
        if code == "cancel":
            state = "TARGET_MENU"
            g.step_out()
            continue
        else:
            t.set_fetch(tags)
            if code == "ok":
                state = "BUILD_MENU"
            else:
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
        else:
            state = "FETCH_MENU"

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
        else:
            state = "BUILD_MENU"

    elif state == "SHOW_SUMMARY":
        code = g.show_summary_menu(t.get_summary())
        if code == "ok":
            state = "DO_FETCH"
        else:
            if not t.fetch_only_run():
                state = "BINARIES_MENU"
            else:
                state = "BUILD_MENU"

    elif state == "DO_FETCH":
        # clear console
        if g:
            subprocess.call("clear")
        t.do_fetch(git_use_depth, git_use_remote)
        state = "DO_BUILD"

    elif state == "DO_BUILD":
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

        t.do_build(toolchains_paths, nthreads)
        state = "HANDLE_BINARIES"

    elif state == "HANDLE_BINARIES":
        state = "DO_COPYFILES"
        if t.fetch_only_run():
            continue
        binaries_path = root_path + "/binaries"
        t.do_get_binaries(binaries_path)

    elif state == "DO_COPYFILES":
        utils.print_message(utils.logtype.INFO, "Working directory: " + root_path)
        out_dir = root_path + "/" + "out_" + t.get_name()
        utils.mkdir_p(out_dir)
        t.do_copyfiles(out_dir)
        state = "DO_IMAGE_GEN"

    elif state == "DO_IMAGE_GEN":
        out_dir = root_path + "/" + "out_" + t.get_name()

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
        utils.print_message(utils.logtype.INFO, "Output directory: ./"
                            + os.path.relpath(out_dir))

if build_log_file is not None:
    build_log_file.close()
