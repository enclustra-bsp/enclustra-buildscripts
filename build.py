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


import os
import sys
import configparser
import subprocess
import shutil
import argparse


import target
import gui
import utils

registered_toolchains = dict()

master_repo_name = "sources"
root_path = os.getcwd()
master_repo_path = root_path + "/" + master_repo_name
state = "INIT"
done = False
build_log_file = None

required_tools = (["make",   "--version", 3, "3.79.1"],
                  ["git",    "--version", 3, "1.7.8"],
                  ["tar",    "--version", 4, "1.15"],
                  ["wget",   "--version", 3, "1.0"])

# initialize utils object

utils = utils.Utils()

# setup argument parser
parser = argparse.ArgumentParser(description="Enclustra's buildsystem")
parser.add_argument("-d", "--device", action='store', required=False,
                    dest='device', metavar='device',
                    help='Device ini file location')

parser.add_argument("--disable-fetch", action='append', required=False,
                    dest='disable_fetch', metavar='target',
                    help='Exclude specific target from fetching')

parser.add_argument("--fetch-history", action='append', required=False,
                    dest='fetch_history', metavar='target',
                    help='Fetch specific target with history')

parser.add_argument("--disable-build", action='append', required=False,
                    dest='disable_build', metavar='target',
                    help='Exclude specific target from building')

parser.add_argument("-t", "--target", action='append', required=False,
                    dest='target', metavar='target',
                    help='Fetch and build on the chosen target')

parser.add_argument("-l", "--list", action='store_true', required=False,
                    dest='list_targets',
                    help='List default targets for chosen device')

parser.add_argument("-L", "--list-all", action='store_true', required=False,
                    dest='list_targets_all',
                    help='List all available targets for chosen device')

parser.add_argument("--list-dev-options", action='store_true', required=False,
                    dest='list_dev_options',
                    help='List all available device options for chosen device')

parser.add_argument("-o", "--dev-option", action='store', required=False,
                    dest='device_option', metavar='option_number',
                    help='Set device option. If unset default will be used')

parser.add_argument("-v", "--version", action='store_true', required=False,
                    dest='version',
                    help='Print version')

# process main config
config = configparser.ConfigParser()
if config.read("enclustra.ini") is None:
    utils.print_message(utils.logtype.ERROR, "Configuration file not found")
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
    utils.print_message(utils.logtype.ERROR, "Configuration file corrupted",
                        str(ext))
    sys.exit(1)


revision = utils.get_git_revision().rstrip('\n')
tool_version = "Enclustra Build Environment (v0.0-" + revision + " (alpha))\n"+ \
                "Running under Python version " \
              + str(sys.version.split()[0]) + "." \
              + "\n\nCopyright (c) 2015 Enclustra GmbH, Switzerland." \
              "\nAll rights reserved."

args = parser.parse_args()

if args.version is True:
    print(str("\n" + tool_version + "\n"))
    sys.exit(0)

# if we're in console mode
elif args.device is not None:
    # initialize target
    dev_path = root_path + "/targets/" + args.device
    parse_dir = root_path + "/targets"
    ini_files = list()
    for directory in (str(args.device)).split("/"):
        parse_dir += "/" + directory
        if os.path.isfile(parse_dir + "/build.ini"):
            ini_files.append(parse_dir + "/build.ini")

    device_name = (str(args.device)).replace("/", "_")
    t = target.Target(master_repo_path, dev_path, ini_files,
                      device_name, debug_calls, utils)
    # if list only
    if args.list_targets is True:
        targets_list = t.get_fetch()
        print(str("Default targets for " + args.device + ":"))
        for tgt in targets_list:
            if tgt[2] is True:
                print(str(tgt[0]))
        sys.exit(0)

    if args.list_targets_all is True:
        targets_list = t.get_fetch()
        print(str("Available targets for " + args.device + ":"))
        for tgt in targets_list:
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
        sys.exit(0)

    if args.target is not None:
        t.set_fetch(args.target)
        t.set_build(args.target)

    if args.disable_fetch is not None:
        t.set_not_fetch(args.disable_fetch)

    if args.disable_build is not None:
        t.set_not_build(args.disable_build)

    if args.fetch_history is not None:
        t.set_fetch_opts(args.fetch_history)

    if args.device_option is not None:
        binaries = t.get_binaries()
        if int(args.device_option) > len(binaries):
            utils.print_message(utils.logtype.ERROR,
                                "Chosen option exceeds available options",
                                "count:", len(binaries))
            sys.exit(1)
        chosen_bin = binaries[int(args.device_option) - 1]
        t.set_binaries(chosen_bin[0])
    else:
        # set the default one
        binaries = t.get_binaries()
        for binary in binaries:
            if binary[2] is True:
                t.set_binaries(binary[0])
                break

    state = "DO_FETCH"
else:
    # if we're in gui mode add dialog to tools list
    required_tools += (["dialog", "--version", 2, "1.1-20120215"], )

# check tools
for tool in required_tools:
    if utils.check_tool(tool[0], tool[1], tool[2], tool[3]) is False:
        utils.print_message(utils.logtype.ERROR, "Version of", tool[0],
                            "has to be", tool[3], "or greater")
        sys.exit(1)

# Git before version 1.8.4 didn't support submodule shallow clone
git_use_depth = utils.check_tool("git", "--version", 3, "1.8.4")
# Git before version 1.8.1.6 didn't use the '--remote' switch in submodules
git_use_remote = utils.check_tool("git", "--version", 3, "1.8.1.6")

# create required folder
try:
    utils.mkdir_p(root_path + "/bin")
except Exception as ex:
    utils.print_message(utils.logtype.ERROR, "Unable to create 'bin' folder",
                        ex)
    sys.exit(1)


# init master repository
subprocess.call("clear")
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
                        "Fetching master repository failed")
    sys.exit(1)

# welcome msg
welcome_msg = tool_version;
# if log file is set this will be logged
utils.print_message(utils.logtype.INFO, welcome_msg + "\n\n")

# Main loop
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
            state = "BINARIES_MENU"
        else:
            state = "FETCH_MENU"

    elif state == "BINARIES_MENU":
        binaries = t.get_binaries()
        # If there are no binaries skip to the next state
        if len(binaries) == 0:
            state = "DO_FETCH"
            continue

        code, tags = g.show_binaries_menu(binaries)
        if code == "ok":
            t.set_binaries(tags)
            state = "DO_FETCH"
        else:
            state = "BUILD_MENU"

    elif state == "DO_FETCH":
        # clear console
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
        binaries_path = root_path + "/binaries"
        t.do_get_binaries(binaries_path)
        state = "DO_COPYFILES"

    elif state == "DO_COPYFILES":
        out_dir = root_path + "/" + "out_" + t.get_name()
        utils.mkdir_p(out_dir)
        t.do_copyfiles(out_dir)
        done = True

if build_log_file is not None:
    build_log_file.close()
