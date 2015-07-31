#! /usr/bin/env python2
# -*- coding: utf-8 -*-

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

# \file build.py
# \brief Enclustra Build Environment target class
# \author Karol Gugala <kgugala@antmicro.com>
# \date 2015-07-03
#
# \copyright Copyright (c) 2015 Enclustra GmbH, Switzerland. All rights reserved.
# \licence This code is released under the Modified BSD licence.

import configparser
import os
import sys
import shutil
import archive


class Target:
    def __init__(self, master_repo_path, config_path, ini_files, target_name,
                 debug_calls, utils):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.master_repo_path = master_repo_path
        self.config_path = config_path
        self.config.read(ini_files)
        self.toolchains = []
        self.targets = dict()
        self.binaries = dict()
        self.bootimage = dict()
        self.parse_init_file()
        self.target_name = str(target_name)
        self.debug_calls = debug_calls
        self.utils = utils

    def get_name(self):
        return self.target_name

    def parse_init_file(self):
        for toolchain in self.config['toolchains']:
            self.toolchains.append(self.config['toolchains'][toolchain])
        # get targets
        for target in self.config['targets']:
            target_descriptor = dict()
            target_build_commands = []
            target_parallelbuild_commands = []
            target_copyfiles = []
            target_help = str(target)
            target_disable = None
            target_active = self.config.getboolean('targets', target)
            target_repository = self.config[target]['repository']

            if self.config.has_option(target, "disables") is True:
                target_disable = self.config[target]["disables"]
            if self.config.has_section(target + "-help") is True:
                if self.config.has_option(target + "-help",
                                          "description") is True:
                    target_help = self.config[target + "-help"]["description"]

            if self.config.has_section(target + "-build") is True:
                for command in self.config[target + "-build"]:
                    target_build_commands.append(self.config[str(target) +
                                                 "-build"][command])

            if self.config.has_section(target + "-parallelbuild") is True:
                for command in self.config[target + "-parallelbuild"]:
                    target_parallelbuild_commands.append(self.config[
                                                         str(target) +
                                                         "-parallelbuild"]
                                                         [command])

            for copyfile in self.config[target + "-copyfiles"]:
                target_copyfiles.append([copyfile, self.config[str(target) +
                                        "-copyfiles"][copyfile]])

            # check if there are some scripts to run
            if str(target + "-scripts") in self.config:
                for script in self.config[target + "-scripts"]:
                    target_descriptor.update([(script, self.config[target +
                                             "-scripts"][script])])

            target_descriptor.update([("help", target_help)])
            target_descriptor.update([("disable", target_disable)])
            target_descriptor.update([("fetch", target_active)])
            target_descriptor.update([("history", False)])
            target_descriptor.update([("build", target_active)])
            target_descriptor.update([("repository", target_repository)])
            target_descriptor.update([("build_commands",
                                     target_build_commands)])
            target_descriptor.update([("parallelbuild_commands",
                                     target_parallelbuild_commands)])
            target_descriptor.update([("copy_files", target_copyfiles)])

            self.targets.update([(target, target_descriptor)])

        # get binaries (if any)
        if self.config.has_section("binaries"):
            for binary in self.config["binaries"]:
                binary_descriptor = dict()
                binary_copyfiles = []

                is_default = self.config.getboolean("binaries", binary)
                download_uri = self.config[binary]["url"]
                unpack = self.config.getboolean(binary, "unpack")
                description = self.config[binary]["description"]
                for copyfile in self.config[binary+"-copyfiles"]:
                    binary_copyfiles.append([copyfile,
                                             self.config[binary + "-copyfiles"]
                                             [copyfile]])

                binary_descriptor.update([("default", is_default)])
                binary_descriptor.update([("description", description)])
                binary_descriptor.update([("uri", download_uri)])
                binary_descriptor.update([("unpack", unpack)])
                binary_descriptor.update([("copy_files", binary_copyfiles)])
                binary_descriptor.update([("chosen", False)])

                self.binaries.update([(binary, binary_descriptor)])

        # get bootimage info
        if self.config.has_section("bootimage"):
            self.bootimage['cmd'] = self.config['bootimage']['bootimage']
            files = []

            if self.config.has_section("bootimage-required-files"):
                for f in self.config['bootimage-required-files']:
                    if self.config.getboolean('bootimage-required-files',f):
                        files.append(f)
            self.bootimage['files'] = files

    def get_bootimage(self):
        return self.bootimage

    def get_binaries(self):
        binaries = []
        for binary in self.binaries:
            binaries.append([(self.binaries[binary])["description"], "",
                            (self.binaries[binary])["default"]])
        return binaries

    def set_binaries(self, bin_desc):
        for binary in self.binaries:
            if (self.binaries[binary])["description"] == bin_desc:
                (self.binaries[binary])["chosen"] = True

    def get_fetch_opts(self):
        fetch_opts = []
        for target in self.targets:
            # if file is marked to fetch we return its opts
            if (self.targets[target])["fetch"] is True:
                fetch_opts.append([target, "",
                                  (self.targets[target])["history"]])
        return fetch_opts

    def set_fetch_opts(self, fetch_opts):
        for target in self.targets:
            (self.targets[target])["history"] = target in fetch_opts

    def get_fetch(self):
        fetch = []
        for target in self.targets:
            help_msg = self.targets[target]["help"]
            if self.targets[target]["disable"] is not None:
                help_msg += " Choosing this target will disable fetching " +\
                            "of the " + self.targets[target]["disable"] + \
                            " target."
            fetch.append([target, "", (self.targets[target])["fetch"],
                         help_msg])
        return fetch

    def handle_disable(self, disable_part):
        for target in self.targets:
            if (self.targets[target])[disable_part] is True:
                disable = (self.targets[target])["disable"]
                if disable is not None:
                    (self.targets[disable])[disable_part] = False

    def set_fetch(self, fetch):
        for target in fetch:
            if not target in self.targets.keys():
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Target does not exist: ",
                                         target)

                available_targets = ", ".join(self.targets)

                self.utils.print_message(self.utils.logtype.INFO,
                                         "Available targets: ",
                                         available_targets)
                sys.exit(1)
        for target in self.targets:
            (self.targets[target])["fetch"] = target in fetch
            # if the target was explicitly set to fetch
            # mark it to build
            if target in fetch:
                (self.targets[target])["build"] = True
        # handle targets disabled by others
        self.handle_disable("fetch")

    def set_not_fetch(self, fetch):
        for target in fetch:
            (self.targets[target])["fetch"] = False
        # handle targets disabled by others
        self.handle_disable("fetch")

    def get_build(self):
        build = []
        for target in self.targets:
            help_msg = self.targets[target]["help"]
            if self.targets[target]["disable"] is not None:
                help_msg += " Choosing this target will disable building " +\
                            "of the " + self.targets[target]["disable"] + \
                            " target."
            build.append([target, "", (self.targets[target])["build"],
                         help_msg])
        return build

    def set_build(self, build):
        for target in build:
            if not target in self.targets.keys():
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Target does not exist: ",
                                         target)

                available_targets = ", ".join(self.targets)

                self.utils.print_message(self.utils.logtype.INFO,
                                         "Available targets: ",
                                         available_targets)
                sys.exit(1)
        for target in self.targets:
            (self.targets[target])["build"] = target in build
        # handle targets disabled by others
        self.handle_disable("build")

    def set_not_build(self, build):
        for target in build:
            (self.targets[target])["build"] = False
        # handle targets disabled by others
        self.handle_disable("build")

    def do_fetch(self, git_use_depth, git_use_remote):
        if git_use_depth is False:
            self.utils.print_message(self.utils.logtype.WARNING,
                                     "Your version of git does not support"
                                     "shallow fetching of a submodule. The"
                                     " repositories will be fetched with a"
                                     " history - this may take a long time."
                                     "Consider upgrading your git version.")
        for target in self.targets:
            if (self.targets[target])["fetch"] is False:
                continue
            self.utils.print_message(self.utils.logtype.INFO, "Fetching",
                                     target)
            # If target is set to fetch w/o history or we have old git version
            if (self.targets[target])["history"] is False\
               and git_use_depth is True:
                depth = "--depth 1"
            else:
                depth = ""

            call = "git submodule init " + (self.targets[target])["repository"]
            with self.utils.cd(self.master_repo_path):
                sp = self.utils.call_tool(call)
            if sp != 0:
                # if fetching failed unmark this target from building
                (self.targets[target])["build"] = False
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "Repository initialization for",
                                         target, "failed")
                continue
            if git_use_remote is True:
                remote = "--remote"
            else:
                remote = ""
            call = "git submodule update " + remote + " " + depth + " " +\
                   (self.targets[target])["repository"]
            with self.utils.cd(self.master_repo_path):
                sp = self.utils.call_tool(call)
            if sp != 0:
                # if fetching failed unmark this target from building
                (self.targets[target])["build"] = False
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "Fetching for", target, "failed")
                continue
            else:
                self.utils.print_message(self.utils.logtype.OK, "Target",
                                         target, "fetched")

            # if there is postfetch custom script
            if "postfetch" in self.targets[target]:
                try:
                    self.utils.run_post_script("fetch", self.targets[target],
                                               self.config_path,
                                               self.master_repo_path)
                except:
                    (self.targets[target])["build"] = False

    def get_required_toolchains(self):
        return self.toolchains

    def call_build_tool(self, command, target, nthreads):
        call = command
        if nthreads != 0:
            call += " -j" + str(nthreads)
        sp = self.utils.call_tool(call)
        if sp != 0:
            self.utils.print_message(self.utils.logtype.ERROR,
                                     "Error running", call,
                                     "for", target)
            # mark as not built
            (self.targets[target])["build"] = False
        else:
            self.utils.print_message(self.utils.logtype.OK, command,
                                     "completed successfully")

    def do_build(self, toolchains_paths, nthreads):
        for target in self.targets:
            if self.targets[target]["build"] is False:
                # skip targets unmarked for building
                self.utils.print_message(self.utils.logtype.INFO,
                                         "Skipping build of target:", target)
                continue
            self.utils.print_message(self.utils.logtype.INFO, "Building",
                                     target)

            with self.utils.cd((self.master_repo_path + "/" +
                               (self.targets[target])["repository"])):
                # store PATH
                orig_path = os.environ["PATH"]
                toolchain_path = ""
                for path in toolchains_paths:
                    toolchain_path += str(path) + ":"
                os.environ["PATH"] = toolchain_path + orig_path

                # build parallel targets
                for command in (self.targets[target])["parallelbuild_commands"]:
                    try:
                        self.call_build_tool(command, target, nthreads)
                    except:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Fail to build:",
                                                 command, "for the target",
                                                 str(target))
                # build parallel targets
                for command in (self.targets[target])["build_commands"]:
                    try:
                        self.call_build_tool(command, target, 0)
                    except:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Fail to build:",
                                                 command, "for the target",
                                                 str(target))

                # restore original PATH
                os.environ["PATH"] = orig_path
                if "postbuild" in self.targets[target]:
                    # copy script file to just fetched repository
                    try:
                        self.utils.run_post_script("build", self.targets[target],
                                                   self.config_path,
                                                   self.master_repo_path)
                    except:
                        (self.targets[target])["build"] = False

    def do_custom_cmd(self, toolchains, custom_dir, custom_cmd):
        # store PATH
        orig_path = os.environ["PATH"]
        toolchain_path = ""
        for path in toolchains:
            toolchain_path += str(path) + ":"
        os.environ["PATH"] = toolchain_path + orig_path

        with self.utils.cd(custom_dir):
            self.utils.call_tool(custom_cmd)

        # restore original PATH
        os.environ["PATH"] = orig_path

    def do_get_binaries(self, dst_path):
        for binary in self.binaries:
            if (self.binaries[binary])["chosen"] is False:
                continue
            self.utils.print_message(self.utils.logtype.INFO, "Getting binary",
                                     binary)
            # create folder
            download_path = dst_path + "/" + binary
            try:
                self.utils.mkdir_p(download_path)
            except:
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Failed to create download folder for",
                                         binary, "binary")
                continue
            # download binary
            binary_file = os.path.basename(self.binaries[binary]["uri"])
            if os.path.isfile(download_path + "/" + binary_file) is False:
                call = "wget " + self.binaries[binary]["uri"]
                with self.utils.cd(download_path):
                    sp = self.utils.call_tool(call)
                if sp != 0:
                    self.utils.print_message(self.utils.logtype.ERROR,
                                             "Error while downloading",
                                             binary, "binary")
                    continue
            # unpack binary (if required)
            if self.binaries[binary]["unpack"] is True:
                with self.utils.cd(download_path):
                    try:
                        a = archive.Archive(os.path.basename(
                                            self.binaries[binary]["uri"]))
                        a.extract()
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Error while unpacking",
                                                 binary, "binary:", exc)
                        continue
            # if everything went OK add path to binary descriptor
            self.binaries[binary].update([("path", download_path)])

    def do_copyfiles(self, dst_path):
        for target in self.targets:
            # do not copy files for targets that weren't built
            if (self.targets[target])["build"] is True:
                self.utils.print_message(self.utils.logtype.INFO,
                                         "Copying files for", target)
                for outfile in (self.targets[target])["copy_files"]:
                    src = self.master_repo_path + "/" +\
                        (self.targets[target])["repository"] +\
                        "/" + outfile[1]
                    dst = dst_path + "/" + outfile[0]
                    try:
                        shutil.copyfile(src, dst)
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Error while copying file",
                                                 src, ":", str(exc))

        # there are some binaries
        if bool(self.binaries) is True:
            self.utils.print_message(self.utils.logtype.INFO,
                                     "Copying binaries")
        # copy binaries
        for binary in self.binaries:
            if not 'path' in self.binaries[binary].keys():
                continue
            for outfile in (self.binaries[binary])["copy_files"]:
                src = self.binaries[binary]["path"] + "/" + outfile[1]
                dst = dst_path + "/" + outfile[0]
                try:
                    shutil.copyfile(src, dst)
                except Exception as exc:
                    self.utils.print_message(self.utils.logtype.WARNING,
                                             "Error while copying file",
                                             src, ":", str(exc))

    def get_summary(self, oneline=False):
        # decide which separator to use
        if oneline:
            line_sep = " "
            node_sep = ", "
        else:
            line_sep = "\n"
            node_sep = "\n"

        # construct device lines
        device_lines_a = []
        device_lines_a.append("Device:")

        device_lines_a.append(self.target_name.replace("_", " "))
        device_lines = line_sep.join(device_lines_a)

        # construct target lines
        target_lines_a = []

        for t in self.targets:
            # skip targets that are not selected
            if not (self.targets[t]["build"] or self.targets[t]["fetch"]):
                continue

            current_target_line = str(t)

            current_target_line += " ("
            # check if target is to be fetched
            if self.targets[t]["fetch"]:
                current_target_line += "fetch"

            # add plus sign if target is to be both fetched and built
            if self.targets[t]["build"] and self.targets[t]["fetch"]:
                current_target_line += " + "

            # check if target is to be built
            if self.targets[t]["build"]:
                current_target_line += "build"
            current_target_line += ")"

            target_lines_a.append(current_target_line)

        target_lines = "Targets:" + line_sep + node_sep.join(target_lines_a)

        # construct binary lines
        binary_lines_a = []

        for b in self.binaries:
            if self.binaries[b]["chosen"]:
                binary_lines_a.append(self.binaries[b]["description"])

        binary_lines = "Binaries:" + line_sep + node_sep.join(binary_lines_a)

        # construct the final summary
        summary = []

        summary.append(device_lines)
        summary.append(target_lines)
        summary.append(binary_lines)

        return (line_sep+"\n").join(summary)
