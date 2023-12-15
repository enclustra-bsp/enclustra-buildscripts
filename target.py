#! /usr/bin/env python2
# -*- coding: utf-8 -*-

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

# \file build.py
# \brief Enclustra Build Environment target class
# \author Karol Gugala <kgugala@antmicro.com>
# \date 2015-07-03
#
# \copyright Copyright (c) 2015-2017 Enclustra GmbH, Switzerland. All rights reserved.
# \licence This code is released under the Modified BSD licence.

import configparser
import os
import sys
import stat
import shutil
import archive
import copy
import tempfile
import subprocess
from utils import Utils


class Target:
    def __init__(self, root_path, master_repo_path, config_path, ini_files,
                 target_name, debug_calls, utils, history_path, release,
                 used_previous_config):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.used_previous_config = used_previous_config
        self.root_path = root_path
        self.master_repo_path = master_repo_path
        self.toolchains = []
        self.targets = dict()
        self.binaries = dict()
        self.const_files = []
        self.bootimages = dict()
        self.clean = dict()
        self.release = release
        self.target_name = str(target_name)
        self.debug_calls = debug_calls
        self.history_path = history_path
        self.utils = utils
        self.out_dir = None

        try:
            self.config_path = config_path
            self.config.read(ini_files)
            self.parse_init_file()
        except configparser.ParsingError as e:
            subprocess.call("clear")
            err_msg = str(e).replace("\n", " ")
            utils.print_message(utils.logtype.ERROR, err_msg)
            # This is a serious error, exit even if exit on error is not set
            sys.exit(1)
        except KeyError as e:
            subprocess.call("clear")
            err_msg = "One of the section is missing a {} key!".format(str(e))
            utils.print_message(utils.logtype.ERROR, err_msg)
            # This is a serious error, exit even if exit on error is not set
            sys.exit(1)

    def save_config(self, filename):
        for t in self.targets:
            key = t + "-options"
            if self.config.has_section(key) is False:
                self.config.add_section(key)

            self.config.set(key, "fetch", str(self.targets[t]["fetch"]))
            self.config.set(key, "fetch_history",
                            str(self.targets[t]["history"]))

            self.config.set(key, "build", str(self.targets[t]["build"]))

            if "build_order" in self.targets[t]:
                self.config.set(key, "build_order", str(self.targets[t]
                                ["build_order"]))

            subtargets = []
            subtargets_p = []
            for s in self.targets[t]["parallelbuild_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len(st) < 1:
                    continue
                subtargets_p.append(st[-1])

            for s in self.targets[t]["build_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len(st) < 1:
                    continue
                subtargets.append(st[-1])

            self.config.set(key, "build_steps", ",".join(subtargets))
            self.config.set(key, "parallelbuild_steps", ",".join(subtargets_p))

        if self.config.has_section("binaries") is True:
            for b in self.config["binaries"]:
                for a in self.binaries:
                     self.config.set(a, "chosen", str(self.binaries[a]["chosen"]))
                self.config.set("binaries", b,
                                str(self.binaries[b]["chosen"]))
                # check if copyfiles were modifies
                # and update config as necessary
                if (self.is_copyfiles_modified(b) and
                        self.config.has_section(b+"-copyfiles")):
                    for i, copyfile in enumerate(self.config[b+"-copyfiles"]):
                        self.config.set(b+"-copyfiles", copyfile,
                                        self.binaries[b]["copy_files"][i][1])
        # set project name
        if self.config.has_section("project") is False:
            self.config.add_section("project")

        self.config.set("project", "name", self.get_name())

        relative_path = self.config_path[len(self.root_path):]

        self.config.set("project", "path", relative_path)

        if not os.path.exists(self.history_path):
            os.makedirs(self.history_path)

        try:
            history_fname = self.history_path + "/" + filename + ".ini"

            cfgfile = open(history_fname, 'w')
            self.config.write(cfgfile)
            self.utils.print_message(self.utils.logtype.INFO,
                                     "History file saved.")
        except:
            self.utils.print_message(self.utils.logtype.WARNING,
                                     "Failed to save history file.")

    def save_project(self, filename, fpath):
        for t in self.targets:
            # do not save targets that were not marked to be fetched
            if not self.targets[t]["fetch"]:
                if self.config.has_section(t):
                    self.config.remove_section(t)
                extra_sects = ["build", "parallelbuild",
                               "help", "copyfiles", "scripts"]
                for e in extra_sects:
                    if self.config.has_section(t + "-" + e):
                        self.config.remove_section(t + "-" + e)

                if self.config.has_option("targets", t):
                    self.config.remove_option("targets", t)

                continue
            key = t + "-options"
            if self.config.has_section(key) is False:
                self.config.add_section(key)

            self.config.set(key, "build", str(False))

            if "build_order" in self.targets[t]:
                self.config.set(key, "build_order", str(self.targets[t]
                                ["build_order"]))

            subtargets = []
            subtargets_p = []
            for s in self.targets[t]["parallelbuild_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len(st) < 1:
                    continue
                subtargets_p.append(st[-1])

            for s in self.targets[t]["build_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len(st) < 1:
                    continue
                subtargets.append(st[-1])

            self.config.set(key, "build_steps", ",".join(subtargets))
            self.config.set(key, "parallelbuild_steps", ",".join(subtargets_p))

        # cleanup the ini file to the required minimum
        if self.config.has_section("binaries") is True:
            for s in self.config["binaries"]:
                self.config.set(s, "chosen", str(self.binaries[s]["chosen"]))
                if self.binaries[s]["chosen"] is True:
                    selected_binary = s
            self.config.remove_section("binaries")
            self.config.add_section("binaries")
            self.config.set("binaries", str(selected_binary), "true")

        if self.config.has_section("targets"):
            for t in self.config["targets"]:
                if self.config.has_section(t + "-scripts"):
                    self.config.remove_section(t + "-scripts")

        # set project name
        if self.config.has_section("project") is False:
            self.config.add_section("project")

        self.config.set("project", "name", self.get_name())

        relative_path = self.config_path[len(self.root_path):]

        self.config.set("project", "path", relative_path)

        if not os.path.exists(fpath):
            os.makedirs(fpath)

        try:
            project_fname = fpath + "/" + filename + ".ini"
            script_fname = fpath + "/" + "build.sh"

            cfgfile = open(project_fname, 'w')
            self.config.write(cfgfile)
            self.utils.print_message(self.utils.logtype.INFO,
                                     "Project file saved.")
            cfgfile.close()

            bfile = open(script_fname, 'w')
            bfile.write("#!/bin/bash\n\n")
            bfile.write("export EBE_RELEASE={}\n".format(self.release))
            bfile.write("cd ..\n")
            bfile.write("./build.sh --build-project " + project_fname + "\n")
            bfile.close()

            bfile_mode = os.stat(script_fname).st_mode
            os.chmod(script_fname, bfile_mode | stat.S_IEXEC)
        except:
            self.utils.print_message(self.utils.logtype.WARNING,
                                     "Failed to save project files.")

    def resave_project(self, project_fname):
        for t in self.targets:
            # only update options
            key = t + "-options"
            if self.config.has_section(key) is False:
                self.config.add_section(key)

            subtargets = []
            subtargets_p = []
            for s in self.targets[t]["parallelbuild_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len(st) < 1:
                    continue
                subtargets_p.append(st[-1])

            for s in self.targets[t]["build_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len(st) < 1:
                    continue
                subtargets.append(st[-1])

            self.config.set(key, "build_steps", ",".join(subtargets))
            self.config.set(key, "parallelbuild_steps", ",".join(subtargets_p))

        try:
            cfgfile = open(project_fname, 'w')
            self.config.write(cfgfile)
            self.utils.print_message(self.utils.logtype.INFO,
                                     "Project file saved.")
            cfgfile.close()
        except:
            self.utils.print_message(self.utils.logtype.WARNING,
                                     "Failed to save project files.")

    def get_name(self):
        return self.target_name

    def parse_init_file(self):
        for toolchain in self.config['toolchains']:
            self.toolchains.append(self.config['toolchains'][toolchain])
        # get targets
        for target in self.config['targets']:
            target_descriptor = dict()
            target_build_commands = []
            target_patches = []
            target_parallelbuild_commands = []
            target_copyfiles = []
            target_help = str(target)
            target_helpbox = None
            target_disable = None
            target_branch = None
            target_fetch = False
            target_fetch_history = False
            target_build = False
            target_active = self.config.getboolean('targets', target)
            target_repository = self.config[target]['repository']
            target_prefetched = False
            target_dt = []
            target_dt_path = []

            try:
                target_priority = int(self.config[target]['priority'])
            except:
                target_priority = 50

            if self.config.has_option(target, "branch") is True:
                target_branch = self.config[target]["branch"]
            else:
                target_branch = self.release

            if self.config.has_option(target, "disables") is True:
                target_disable = self.config[target]["disables"]
            if self.config.has_section(target + "-help") is True:
                if self.config.has_option(target + "-help",
                                          "description") is True:
                    target_help = self.config[target + "-help"]["description"]
                if self.config.has_option(target + "-help",
                                          "box") is True:
                    target_helpbox = self.config[target + "-help"]["box"]

            key = target + "-options"

            # check if target is configured
            # this is needed in next step
            target_configured = os.path.isfile(
                                    os.path.join(self.master_repo_path,
                                                 target_repository,
                                                 ".config"))

            if self.config.has_section(target + "-device-tree") is True:
                for command in self.config[target + "-device-tree"]:
                    subtarget = dict()
                    if command == "path":
                        subtarget['path'] = self.config[str(target) +
                                                   "-device-tree"][command]
                        target_dt_path.append(subtarget)
                    else:
                        subtarget['cmd'] = self.config[str(target) +
                                                   "-device-tree"][command]
                        target_dt.append(subtarget)
	    
            if self.config.has_section(target + "-build") is True:
                for command in self.config[target + "-build"]:
                    subtarget = dict()
                    subtarget['name'] = target + " " + command
                    subtarget['cmd'] = self.config[str(target) +
                                                   "-build"][command]

                    subtarget['enabled'] = True
                    # do not run defconfig when using saved config
                    # and the target is already configured
                    if ("defconfig" in command and
                            self.used_previous_config and target_configured):
                        subtarget['enabled'] = False

                    target_build_commands.append(subtarget)

            if self.config.has_section(target + "-parallelbuild") is True:
                for command in self.config[target + "-parallelbuild"]:
                    subtarget = dict()
                    subtarget['name'] = target + " " + command
                    subtarget['cmd'] = self.config[str(target) +
                                                   "-parallelbuild"][command]
                    subtarget['enabled'] = True
                    # do not run defconfig when using saved config
                    # and the target is already configured
                    if ("defconfig" in command and
                            self.used_previous_config and target_configured):
                        subtarget['enabled'] = False

                    target_parallelbuild_commands.append(subtarget)

            if self.config.has_section(key) is True:
                if self.config.has_option(key, "fetch"):
                    target_fetch = self.config.getboolean(key, "fetch")
                if self.config.has_option(key, "fetch_history"):
                    target_fetch_history = \
                        self.config.getboolean(key, "fetch_history")

                if self.config.has_option(key, "build"):
                    target_build = self.config.getboolean(key, "build")
                if self.config.has_option(key, "prefetched"):
                    target_prefetched = self.config.getboolean(key, "prefetched")


            if self.config.has_section(target + "-patches") is True:
                for patch in self.config[target + "-patches"]:
                    target_patches.append(self.config[str(target) +
                                          "-patches"][patch])

            for copyfile in self.config[target + "-copyfiles"]:
                target_copyfiles.append([copyfile, self.config[str(target) +
                                        "-copyfiles"][copyfile]])

            # check if there are some scripts to run
            if str(target + "-scripts") in self.config:
                for script in self.config[target + "-scripts"]:
                    target_descriptor.update([(script, self.config[target +
                                             "-scripts"][script])])

            target_descriptor.update([("help", target_help)])
            target_descriptor.update([("helpbox", target_helpbox)])
            target_descriptor.update([("disable", target_disable)])
            target_descriptor.update([("fetch", target_fetch)])
            target_descriptor.update([("disable_fetch", False)])
            target_descriptor.update([("prefetched", target_prefetched)])
            target_descriptor.update([("history", target_fetch_history)])
            target_descriptor.update([("build", target_build)])
            target_descriptor.update([("active", target_active)])
            target_descriptor.update([("disable_build", False)])
            target_descriptor.update([("build_error", False)])
            target_descriptor.update([("repository", target_repository)])
            target_descriptor.update([("priority", target_priority)])
            target_descriptor.update([("branch", target_branch)])
            target_descriptor.update([("patches", target_patches)])
            target_descriptor.update([("build_commands",
                                     target_build_commands)])
            target_descriptor.update([("parallelbuild_commands",
                                     target_parallelbuild_commands)])
            target_descriptor.update([("copy_files", target_copyfiles)])
            target_descriptor.update([("device-tree", target_dt)])
            target_descriptor.update([("device-tree-path", target_dt_path)])

            self.targets.update([(target, target_descriptor)])

        if self.config.has_section("clean") is True:
            for target in self.config["clean"]:
                self.clean[target] = self.config["clean"][target]

        # get binaries (if any)
        if self.config.has_section("binaries"):
            for binary in self.config["binaries"]:
                binary_descriptor = dict()
                binary_copyfiles = []
                binary_copyfiles_init = []
                binary_copyfiles_def = []

                is_default = self.config.getboolean("binaries", binary)
                download_uri = self.config[binary]["url"]
                if self.config.has_option(binary, "shortname"):
                    shortname = self.config[binary]["shortname"]
                else:
                    shortname = binary
                if self.config.has_option(binary, "force_download"):
                    redownload = self.config.getboolean(binary,
                                                        "force_download")
                else:
                    redownload = False
                unpack = self.config.getboolean(binary, "unpack")
                description = self.config[binary]["description"]
                if self.config.has_option(binary, "chosen"):
                    chosen = self.config[binary]["chosen"]
                else:
                    chosen = False
                if self.config.has_option(binary, "helpbox"):
                    helpbox = self.config[binary]["helpbox"]
                else:
                    helpbox = None

                if self.config.has_section(binary+"-copyfiles"):
                    for copyfile in self.config[binary+"-copyfiles"]:
                        binary_copyfiles.append([copyfile,
                                                 self.config[
                                                    binary + "-copyfiles"]
                                                 [copyfile]])
                    binary_copyfiles_init = copy.deepcopy(binary_copyfiles)
                else:
                    binary_copyfiles = None
                    binary_copyfiles_init = None

                if self.config.has_section(binary+"-copyfiles-default"):
                    for copyf_def in self.config[binary+"-copyfiles-default"]:
                        binary_copyfiles_def.append([copyf_def,
                                                    self.config[binary +
                                                     "-copyfiles-default"]
                                                     [copyf_def]])
                else:
                    # no default section for copyfiles
                    # set current copyfiles to be default
                    # and update config section
                    binary_copyfiles_def = copy.deepcopy(binary_copyfiles)
                    if binary_copyfiles is not None:
                        self.config.add_section(binary+"-copyfiles-default")
                        for copyfile in self.config[binary+"-copyfiles"]:
                            self.config.set(binary+"-copyfiles-default",
                                            copyfile,
                                            self.config[binary + "-copyfiles"]
                                            [copyfile])

                # get device-tree for each target individually
                for target in self.config['targets']:
                    binary_dt = []
                    if self.config.has_section(binary + "-" + target + "-device-tree"):
                        for dt in self.config[binary + "-" + target + "-device-tree"]:
                            subtarget = dict()
                            subtarget['cmd'] = self.config[binary + "-" + target + "-device-tree"][dt]
                            binary_dt.append(subtarget)
                    binary_descriptor.update([(target + "-device-tree", binary_dt)])

                binary_descriptor.update([("default", is_default)])
                binary_descriptor.update([("description", description)])
                binary_descriptor.update([("helpbox", helpbox)])
                binary_descriptor.update([("uri", download_uri)])
                binary_descriptor.update([("unpack", unpack)])
                binary_descriptor.update([("redownload", redownload)])
                binary_descriptor.update([("shortname", shortname)])
                binary_descriptor.update([("copy_files", binary_copyfiles)])
                binary_descriptor.update([("copy_files-init",
                                         binary_copyfiles_init)])
                binary_descriptor.update([("copy_files-default",
                                         binary_copyfiles_def)])
                binary_descriptor.update([("chosen", bool(chosen))])

                self.binaries.update([(binary, binary_descriptor)])

        # get non-modifiable binaries
        if self.config.has_section("binaries-non-modifiable"):
            for binary in self.config["binaries-non-modifiable"]:
                if self.config.getboolean("binaries-non-modifiable", binary):
                    self.const_files.append(binary)

        # get bootimage info
        if self.config.has_section("bootimage"):
            for k in self.config['bootimage']:
                self.bootimages[k] = dict()
                self.bootimages[k]['cmd'] = self.config['bootimage'][k]
                files = []
                result_files = []

                if self.config.has_section(k + "-required-files"):
                    for f in self.config[k + '-required-files']:
                        if self.config.getboolean(k + '-required-files', f):
                            files.append(f)
                if self.config.has_section(k + "-required-files"):
                    for f in self.config[k + '-result-files']:
                        if self.config.getboolean(k + '-result-files', f):
                            result_files.append(f)
                self.bootimages[k]['files'] = files
                self.bootimages[k]['result_files'] = result_files

    def clean_targets(self, targets):
        for t in targets:
            if t not in self.clean:
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "No clean command for",
                                         t, "target defined")
                continue

            self.utils.print_message(self.utils.logtype.INFO,
                                     "Running clean command for",
                                     t, "target")

            with self.utils.cd((self.master_repo_path + "/" +
                               (self.targets[t])["repository"])):
                # build parallel targets
                self.utils.call_tool(self.clean[t])

    def get_target_helpbox(self, target):
        try:
            return self.targets[target]["helpbox"]
        except KeyError:
            return "No help available for " + target

    def get_binary_helpbox(self, binary):
        for b in self.binaries:
            if self.binaries[b]["description"] == binary:
                return self.binaries[b]["helpbox"]
        return None

    def get_bootimages(self):
        return self.bootimages

    def get_binaries(self):
        binaries = []
        for binary in self.binaries:
            custom = self.is_copyfiles_default(binary)
            binaries.append([(self.binaries[binary])["description"],
                             "(custom)" if custom else "(default)"])

        return binaries

    def get_binary_srcpath(self, chosen_bin_file):
        src_path = ""
        # Search for selected file in chosen binaries set
        for b in self.binaries:
            if self.binaries[b]["chosen"]:
                for outfile in self.binaries[b]["copy_files"]:
                    if chosen_bin_file == outfile[0]:
                        if os.path.isabs(outfile[1]):
                            src_path = outfile[1]
                        else:
                            # If default binary used, return current dir
                            # This is because the path of default binary
                            # is unknown here as it is passed from build.py
                            src_path = os.getcwd()
        if os.path.isdir(src_path) and not src_path.endswith(os.sep):
            src_path += os.sep
        return src_path

    def get_marked_binaries(self):
        binaries = []
        for binary in self.binaries:
            b = dict()
            b['name'] = binary
            b["description"] = (self.binaries[binary])["description"]
            b["default"] = (self.binaries[binary])["default"]
            b["copyfiles"] = copy.deepcopy(
                                (self.binaries[binary])["copy_files"])
            binaries.append(b)

        return binaries

    def get_default_binary(self):
        for binary in self.binaries:
            if self.binaries[binary]["default"]:
                return (self.binaries[binary])["description"]

    def set_binaries(self, bin_desc):
        for binary in self.binaries:
            (self.binaries[binary])["chosen"] = \
                ((self.binaries[binary])["description"] == bin_desc)

    def set_binaries_copyfile(self, chosen_bin_file, new_bin_file):
        for b in self.binaries:
            if self.binaries[b]["chosen"]:
                for i, f in enumerate(self.binaries[b]["copy_files"]):
                    if chosen_bin_file == f[0]:
                        (self.binaries[b]["copy_files"])[i][1] = new_bin_file
                        return True
        return False

    def set_binaries_copyfile_default(self, copyfile=None):
        # reset binaries to default values
        for b in self.binaries:
            if self.binaries[b]["chosen"]:
                if copyfile is not None:
                    # search for copyfile and set it to default
                    for i, cf in enumerate(self.binaries[b]["copy_files"]):
                        if cf[0] == copyfile:
                            cf[1] = \
                                self.binaries[b]["copy_files-default"][i][1]
                            break
                else:
                    # set all copyfiles to default
                    self.binaries[b]["copy_files"] = \
                        copy.deepcopy(self.binaries[b]["copy_files-default"])

    def set_binaries_copyfile_init(self):
        # drop changes done to copyfiles in current session
        for b in self.binaries:
            if self.binaries[b]["chosen"]:
                self.binaries[b]["copy_files"] = \
                    copy.deepcopy(self.binaries[b]["copy_files-init"])

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

    def get_build_opts(self, option):
        build_opts = []

        for target in self.targets:
            if not self.targets[target]["active"]:
                continue
            for subt in (self.targets[target])["parallelbuild_commands"]:
                if option == subt['name'].split(" ")[1]:
                    build_opts.append([subt['name'], "", subt['enabled']])
            for subt in (self.targets[target])["build_commands"]:
                if option == subt['name'].split(" ")[1]:
                    build_opts.append([subt['name'], "", subt['enabled']])
        return build_opts

    def get_subtargets(self, target):
        build_opts = []

        if (self.targets[target])["build"] is True:
            for subt in (self.targets[target])["parallelbuild_commands"]:
                build_opts.append(subt['name'])
            for subt in (self.targets[target])["build_commands"]:
                build_opts.append(subt['name'])
        return build_opts

    def get_config_overwrite(self, targets):
        overwrite_string = ""
        try:
            if self.used_previous_config:
                for t in targets:
                    if(self.is_target_configured(t) and
                            self.is_build_opt_set(t, t+" defconfig")):
                        if overwrite_string == "":
                            overwrite_string = t
                        else:
                            overwrite_string += " and " + t
        except Exception as e:
            pass
        return overwrite_string

    def is_build_opt_set(self, target, opt):
        for c in (self.targets[target])["parallelbuild_commands"]:
            if c['name'] == opt:
                return c['enabled']
        for c in (self.targets[target])["build_commands"]:
            if c['name'] == opt:
                return c['enabled']
        return False

    def validate_subtargets(self, subtargets):
        invalid = []
        invalid.extend(subtargets)
        for target in self.targets:
            for c in (self.targets[target])["parallelbuild_commands"]:
                if c['name'] in subtargets:
                    invalid.remove(c['name'])
            for c in (self.targets[target])["build_commands"]:
                if c['name'] in subtargets:
                    invalid.remove(c['name'])
        return invalid

    def set_build_opts(self, build_opts, option="all"):
        for target in self.targets:
            for c in (self.targets[target])["parallelbuild_commands"]:
                if option == "all" or option in c['name']:
                    c['enabled'] = c['name'] in build_opts
            for c in (self.targets[target])["build_commands"]:
                if option == "all" or option in c['name']:
                    c['enabled'] = c['name'] in build_opts

    def get_fetch(self):
        fetch = []
        for target in self.targets:
            if not self.targets[target]["active"]:
                continue
            if self.targets[target]["prefetched"]:
                continue
            help_msg = "Fetch " + self.targets[target]["help"]
            fetch.append([target, "",
                         (self.targets[target])["fetch"],
                         help_msg])
        return fetch

    def handle_disable(self, disable_part):
        for target in self.targets:
            if (self.targets[target])[disable_part] is True:
                disable = (self.targets[target])["disable"]
                if disable is not None:
                    (self.targets[disable])["disable_"+disable_part] = True

    def set_fetch(self, fetch):
        for target in fetch:
            if target not in self.targets.keys():
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Target does not exist:",
                                         target)

                available_targets = ", ".join(self.targets)

                self.utils.print_message(self.utils.logtype.INFO,
                                         "Available targets:",
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
            if not self.targets[target]["active"]:
                continue
            help_msg = "Build " + self.targets[target]["help"]
            if self.targets[target]["disable"] is not None:
                help_msg += " Choosing this target will disable building " +\
                            "of the " + self.targets[target]["disable"] + \
                            " target."
            build.append([target, "",
                         (self.targets[target])["build"],
                         help_msg])
        return build

    def set_build(self, build):
        for target in build:
            if target not in self.targets.keys():
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Target does not exist:",
                                         target)

                available_targets = ", ".join(self.targets)

                self.utils.print_message(self.utils.logtype.INFO,
                                         "Available targets:",
                                         available_targets)
                sys.exit(1)
        for target in self.targets:
            (self.targets[target])["build"] = target in build
        # handle targets disabled by others
        self.handle_disable("build")

    def set_active_targets(self):
        for target in self.targets:
            (self.targets[target])["fetch"] = (self.targets[target])["active"]
            (self.targets[target])["build"] = (self.targets[target])["active"]
        # handle targets disabled by others
        self.handle_disable("fetch")
        self.handle_disable("build")

    def set_not_build(self, build):
        for target in build:
            (self.targets[target])["build"] = False
        # handle targets disabled by others
        self.handle_disable("build")

    def is_copyfiles_modified(self, binary):
        # check if copyfiles for selected binaries set
        # were modified by comparing current and initial
        return (self.binaries[binary]["copy_files"] !=
                self.binaries[binary]["copy_files-init"])

    def is_copyfiles_default(self, binary):
        # check if we use default, unmodified binaries set
        return (self.binaries[binary]["copy_files"] !=
                self.binaries[binary]["copy_files-default"])

    def is_copyfiles_all_custom(self, binary):
        # check if all binary files in binary set are custom
        all_custom = True
        try:
            for cf in self.binaries[binary]["copy_files"]:
                if not os.path.isabs(cf[1]):
                    all_custom = False
        except TypeError:
            all_custom = False
        return all_custom

    def is_target_configured(self, target):
        return os.path.isfile(os.path.join(self.master_repo_path,
                              self.targets[target]["repository"],
                              ".config"))

    def do_fetch(self, git_use_depth, git_use_remote):
        if git_use_depth is False:
            self.utils.print_message(self.utils.logtype.WARNING,
                                     "Your version of git does not support"
                                     "shallow fetching of a submodule. The"
                                     " repositories will be fetched with a"
                                     " history - this may take a long time."
                                     "Consider upgrading your git version.")
        for target in sorted(self.targets,
                             key=lambda t: self.targets[t]["priority"]):
            if (self.targets[target])["fetch"] is False:
                continue
            if (self.targets[target])["disable_fetch"] is True:
                continue
            if (self.targets[target])["prefetched"] is True:
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
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "Fetching for", target, "failed")
                continue

            # Switch branch if specified
            if (self.targets[target])["branch"] is not None:
                call = "git fetch " + depth + " origin " + \
                       (self.targets[target])["branch"]

                repo_dir = \
                    self.master_repo_path + "/" + \
                    str((self.targets[target])["repository"])

                with self.utils.cd(repo_dir):
                    sp = self.utils.call_tool(call)
                call = "git checkout FETCH_HEAD"
                if sp == 0:
                    with self.utils.cd(repo_dir):
                        sp = self.utils.call_tool(call)
            if sp != 0:
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "Fetching for", target, "failed")
                continue

            self.utils.print_message(self.utils.logtype.OK, "Target",
                                     target, "fetched")

            # if there is postfetch custom script
            if "postfetch" in self.targets[target]:
                try:
                    self.utils.run_script("postfetch", self.targets[target],
                                          self.config_path,
                                          self.master_repo_path)
                except:
                    (self.targets[target])["build"] = False

    def get_required_toolchains(self):
        return self.toolchains

    def call_build_tool(self, command, target, nthreads):
        call = command.replace("${OUTDIR}", self.out_dir)
        if nthreads != 0:
            call += " -j" + str(nthreads)
        try:
            sp = self.utils.call_tool(call)
            if sp != 0:
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Error running", call,
                                         "for", target)
                # mark as not built
                (self.targets[target])["build"] = False
                # set build error
                (self.targets[target])["build_error"] = True
            else:
                self.utils.print_message(self.utils.logtype.OK, command,
                                         "completed successfully")
        except Exception as exc:
            self.utils.print_message(self.utils.logtype.ERROR,
                                     "Error while running", call,
                                     "for", target, ":", str(exc))
            # mark as not built
            (self.targets[target])["build"] = False
            # set build error
            (self.targets[target])["build_error"] = True

    def string_exists_in_file(self, string, file):
        with open(file, "r") as fp:
            lines = fp.readlines()
            for line in lines:
                if line.find(string) != -1:
                    return True
        return False

    def apply_patch(self, target):
        target_folder = self.master_repo_path + "/"\
            + (self.targets[target])["repository"]
        for patch in self.targets[target]["patches"]:
            patch_path = target_folder + "/" + patch
            # if the patch file is already in the target folder
            # we assume that the sources has been already patched
            if os.path.isfile(patch_path):
                continue
            # copy the patch file
            try:
                shutil.copyfile(self.config_path + "/" + patch,
                                patch_path)
            except Exception as exc:
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Error while copying patch file",
                                         patch, "for the target",
                                         str(target), ":", str(exc))
                return 1
            # pach the code
            try:
                with self.utils.cd(target_folder):
                    call = "git --apply " + patch
                    sp = self.utils.call_tool(call)
                    if sp != 0:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Error while patching target",
                                                 str(target), "with patch",
                                                 patch)
                        return 1

            except Exception as exc:
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Error while patching target",
                                         str(target), "with patch",
                                         patch, ":", str(exc))
                return 1
        # everything went OK
        return 0

    def do_build(self, toolchains_paths, nthreads):
        for target in sorted(self.targets,
                             key=lambda t: self.targets[t]["priority"]):
            if self.targets[target]["build"] is False:
                # skip targets unmarked for building
                self.utils.print_message(self.utils.logtype.INFO,
                                         "Skipping build of target:", target)
                continue
            if self.targets[target]["disable_build"] is True:
                continue
            self.utils.print_message(self.utils.logtype.INFO, "Building",
                                     target)
            if self.targets[target]["patches"] is not None:
                if self.apply_patch(target) != 0:
                    # if patching failed, do not build this target
                    self.targets[target]["build"] = False
                    self.targets[target]["build_error"] = True
                    continue

            # init variables for device-tree
            device_tree = []
            dt_path = []

            # get device-tree list
            if self.targets[target]["device-tree"] is not None:
                for dt in (self.targets[target])["device-tree"]:
                    device_tree.append(dt['cmd'])

            # get device tree list from binary section
            for binary in self.binaries:
                if self.binaries[binary]["chosen"] is True:
                    if self.binaries[binary][target + "-device-tree"] is not None:
                        for dt in self.binaries[binary][target + "-device-tree"]:
                            device_tree.append(dt['cmd'])

            # get device tree path
            if self.targets[target]["device-tree-path"]:
                dt_path = self.targets[target]["device-tree-path"][0]['path']

            # create device-tree only if files and path are specified for this target
            if device_tree and dt_path:

                # create dts file, it contains includes for all the required dtsi files
                dtb = open(self.master_repo_path + "/" + self.targets[target]["repository"] + "/" +
			   dt_path + "/enclustra_generated.dts", "w")
                # write header to dts file, 
                dtb.write("/* AUTOGENERATED FILE - DO NOT MODIFY */\n")
                dtb.write("/* This file is created by Enclustra Build Environment */\n\n")

                # A file defining /dts-v1/ must be included at beginning
                insert_version_identifier = True
                dts_file_containing_version_identifier = ""
                for dt in device_tree:
                    full_file_path = self.master_repo_path + "/" + self.targets[target]["repository"] + "/" + dt_path + "/" + dt
                    if os.path.isfile(full_file_path):
                        if self.string_exists_in_file("/dts-v1/;", full_file_path):
                            dtb.write("#include \"" + dt + "\"\n")
                            dts_file_containing_version_identifier = dt
                            insert_version_identifier = False
                            break

                # remove dts from list to make sure it does not get added a second time
                if dts_file_containing_version_identifier:
                    device_tree.remove(dts_file_containing_version_identifier)

                # add version identifier if not already added in one of the include files
                if insert_version_identifier:
                    dtb.write("/dts-v1/;\n\n")

                # include the device tree for the module at the end (module device tree name starts with ME- or MA-)
                for dt in device_tree:
                    if "MA-" not in dt and "ME-" not in dt and "AM-" not in dt:
                        dtb.write("#include \"" + dt + "\"\n")
                for dt in device_tree:
                    if "MA-" in dt or "ME-" in dt or "AM-" in dt:
                        dtb.write("#include \"" + dt + "\"\n")

                dtb.close()
                self.utils.print_message(self.utils.logtype.OK, target + " device-tree " + dt_path +
					 "/enclustra_generated.dts created successfully")
            elif device_tree:
                self.utils.print_message(self.utils.logtype.ERROR, target + "device-tree can not be added without path")

            with self.utils.cd((self.master_repo_path + "/" +
                               (self.targets[target])["repository"])):
                # check if the repository is fetched
                if not os.path.exists(".git"):
                    msg = "Attempting build of target: " + target
                    msg += ", but the repository is not fetched"
                    self.utils.print_message(self.utils.logtype.ERROR, msg)
                    (self.targets[target])["build"] = False
                    (self.targets[target])["build_error"] = True
                    continue

                if "prebuild" in self.targets[target]:
                    # copy script file to just fetched repository
                    try:
                        self.utils.run_script("prebuild",
                                              self.targets[target],
                                              self.config_path,
                                              self.master_repo_path)
                    except:
                        (self.targets[target])["build"] = False
                        (self.targets[target])["build_error"] = True

                # store PATH
                orig_path = os.environ["PATH"]
                toolchain_path = ""
                for path in toolchains_paths:
                    toolchain_path += str(path) + ":"
                os.environ["PATH"] = toolchain_path + orig_path

                key = target + "-options"
                if self.config.has_option(key, "build_order"):
                    # build targets according to defined order
                    count_subt_parallel = 0
                    count_subt_build = 0
                    for subt in self.config.get(key, "build_order").split(","):
                        sub_option = target + " " + subt
                        sub_found = False
                        for partar in (self.targets[target])[
                                       "parallelbuild_commands"]:
                            if partar['name'] == sub_option:
                                # build parallel targets
                                if partar['enabled']:
                                    self.call_build_tool(partar['cmd'],
                                                     target, nthreads)
                                sub_found = True
                                count_subt_parallel += 1
                                break

                        # All targets from the build order section
                        # have to be defined either in the build
                        # or the parallel build section
                        if sub_found:
                            continue
                        for btar in (self.targets[target])["build_commands"]:
                            if btar['name'] == sub_option:
                                # build targets
                                if partar['enabled']:
                                    self.call_build_tool(btar['cmd'], target, 0)
                                sub_found = True
                                count_subt_build += 1
                                break

                        if sub_found:
                            continue
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Undefined subtarget",
                                                 sub_option, "referenced "
                                                 "in the build order")

                    if count_subt_parallel < len((self.targets[target])[
                                                  "parallelbuild_commands"]):
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Not all", target,
                                                 "parallelbuild targets are "
                                                 "included in the build "
                                                 "order section")
                    if count_subt_build < len((self.targets[target])[
                                               "build_commands"]):
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Not all", target, "build "
                                                 "targets are included in the "
                                                 "build_order section")
                else:
                    # build parallel targets
                    for subt in (self.targets[target])[
                                 "parallelbuild_commands"]:
                        if subt['enabled']:
                            self.call_build_tool(subt['cmd'], target, nthreads)
                    # build targets
                    for subt in (self.targets[target])["build_commands"]:
                        if subt['enabled']:
                            self.call_build_tool(subt['cmd'], target, 0)

                # restore original PATH
                os.environ["PATH"] = orig_path
                if "postbuild" in self.targets[target]:
                    # copy script file to just fetched repository
                    try:
                        self.utils.run_script("postbuild",
                                              self.targets[target],
                                              self.config_path,
                                              self.master_repo_path)
                    except:
                        (self.targets[target])["build"] = False
                        (self.targets[target])["build_error"] = True

    def do_custom_cmd(self, toolchains, custom_dir, custom_cmd):
        # store PATH
        orig_path = os.environ["PATH"]
        toolchain_path = ""
        for path in toolchains:
            toolchain_path += str(path) + ":"
        os.environ["PATH"] = toolchain_path + orig_path

        with self.utils.cd(custom_dir):
            sp = self.utils.call_tool(custom_cmd)

        # restore original PATH
        os.environ["PATH"] = orig_path
        return sp

    def fetch_only_run(self):
        for target in self.targets:
            if (self.targets[target])["build"]:
                return False
        return True

    def do_get_binaries(self, dst_path):
        if self.fetch_only_run():
            return
        for binary in self.binaries:
            if (self.binaries[binary])["chosen"] is False:
                continue
            if (self.is_copyfiles_all_custom(binary)):
                # all binary files are custom - we can skip
                continue
            self.utils.print_message(self.utils.logtype.INFO, "Getting binary",
                                     binary)
            # create folder
            download_path = dst_path + "/" + binary
            try:
                self.utils.mkdir_p(download_path)
            except:
                self.utils.print_message(self.utils.logtype.ERROR,
                                         "Failed to create download folder",
                                         "for", binary, "binary")
                continue
            # download binary
            binary_file = os.path.basename(self.binaries[binary]["uri"])
            call = "curl -L -O "
            if self.binaries[binary]["redownload"] is False:
                call = call + "-z " + download_path + "/" + binary_file
            elif os.path.isfile(download_path + "/" + binary_file):
                os.remove(download_path + "/" + binary_file)
            call = call + " " + self.binaries[binary]["uri"]
            temp_path = tempfile.mkdtemp()

            with self.utils.cd(temp_path):
                sp = self.utils.call_tool(call)
                if sp == 0:
                    # see if it is downloaded
                    if os.path.exists(temp_path + "/" + binary_file):
                        self.utils.print_message(Utils.logtype.INFO,
                                                 "New version of",
                                                 binary_file,
                                                 "downloaded.")
                        # everything ok, copy to real destination
                        shutil.copy(temp_path + "/" + binary_file,
                                        download_path + "/")
                    else:
                        self.utils.print_message(Utils.logtype.INFO,
                                                 "No new version of",
                                                 binary_file,
                                                 "available")

            shutil.rmtree(temp_path)

            if sp != 0:
                # We could not download file, check if an older version exist
                can_use_older = True
                for cp_file in self.binaries[binary]['copy_files']:
                    if not os.path.exists(download_path + "/" + cp_file[1]):
                        can_use_older = False
                        break

                if can_use_older:
                    self.utils.print_message(self.utils.logtype.WARNING,
                                             "Could not download an updated",
                                             binary,
                                             "binary, using an older version")
                else:
                    self.utils.print_message(self.utils.logtype.ERROR,
                                             "Error while downloading",
                                             binary,
                                             "binary")
                    continue
            # unpack binary (if required)
            if self.binaries[binary]["unpack"] is True:
                with self.utils.cd(download_path):
                    try:
                        a = archive.Archive(os.path.basename(
                                            self.binaries[binary]["uri"]))
                        a.extract()
                    except Exception as exc:
                        # the downloaded file is corrupted, delete it
                        shutil.rmtree(download_path)

                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Error while unpacking",
                                                 binary, "binary:", exc,
                                                 "- deleting.")
                        continue
            # if everything went OK add path to binary descriptor
            self.binaries[binary].update([("path", download_path)])

    def do_copyfiles(self):
        for target in self.targets:
            # do not copy files for targets that weren't built
            if (self.targets[target])["build"] is True:
                self.utils.print_message(self.utils.logtype.INFO,
                                         "Copying files for", target)
                for outfile in (self.targets[target])["copy_files"]:
                    src = self.master_repo_path + "/" +\
                        (self.targets[target])["repository"] +\
                        "/" + outfile[1]
                    dst = self.out_dir + "/" + outfile[0]
                    dstdir = "/".join(dst.split("/")[:-1])

                    dstdir = os.path.abspath(dstdir)

                    if dstdir.startswith(self.out_dir) is False:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Destination file out of",
                                                 "output directory")
                        continue

                    self.utils.mkdir_p(dstdir)

                    try:
                        shutil.copyfile(src, dst)
                        shutil.copymode(src, dst)
                        self.utils.print_message(self.utils.logtype.INFO,
                                                 "Copying ./" +
                                                 os.path.relpath(src) +
                                                 " to ./" +
                                                 os.path.relpath(dst))
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Error while copying file",
                                                 src, ":", str(exc))

            # delete any existing previous products of failed builds
            if (self.targets[target])["build_error"] is True:
                for outfile in (self.targets[target])["copy_files"]:
                    file_path = self.out_dir + "/" + outfile[0]
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Error while deleting file",
                                                 file_path, ":", str(exc))
    def do_copybinaries(self):

        # there are some binaries
        if bool(self.binaries) and not self.fetch_only_run():
            self.utils.print_message(self.utils.logtype.INFO,
                                     "Copying binaries")
        # copy binaries
        for binary in self.binaries:
            # copy files only for chosen binary set
            if not self.binaries[binary]['chosen']:
                continue
            # path is set only when download was successfull
            # so skip copying if it's unset
            if ('path' not in self.binaries[binary].keys() and
                    not self.is_copyfiles_all_custom(binary)):
                continue
            if (self.binaries[binary])["copy_files"] is not None:
                for outfile in (self.binaries[binary])["copy_files"]:
                    if os.path.isabs(outfile[1]):
                        src = outfile[1]
                    else:
                        src = self.binaries[binary]["path"] + "/" + outfile[1]
                    dst = self.out_dir + "/" + outfile[0]
                    try:
                        if os.path.isfile(src):
                            shutil.copyfile(src, dst)
                        if os.path.isdir(src):
                            if os.path.isdir(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        self.utils.print_message(self.utils.logtype.INFO,
                                                 "Copying ./" +
                                                 os.path.relpath(src) +
                                                 " to ./" +
                                                 os.path.relpath(dst))
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Error while copying file",
                                                 src, ":", str(exc))
            else:
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "No binary files to copy found")

    def do_generate_image(self, directory, toolchains_paths):
        bootimages = self.get_bootimages()

        for k in bootimages.keys():
            generate_img = True
            # there is no bootimage to build
            if 'cmd' not in bootimages[k].keys():
                return

            # check if every required file is accessible
            missing_files = []
            with self.utils.cd(directory):
                for f in bootimages[k]['files']:
                    if not os.path.isfile(f):
                        missing_files.append(f)

            if len(missing_files):
                generate_img = False
                info_msg = "Skipping generation of bootimage:"
                self.utils.print_message(self.utils.logtype.INFO,
                                         info_msg, k)
                info_msg = "The missing files are:"
                missing_files = ", ".join(missing_files)
                self.utils.print_message(self.utils.logtype.INFO,
                                         info_msg, missing_files)

            # if dependancies are met
            if generate_img:
                self.utils.print_message(self.utils.logtype.INFO,
                                         "Generating boot image")
                sp = self.do_custom_cmd(toolchains_paths,
                                        directory,
                                        bootimages[k]['cmd'])
                if sp != 0:
                    self.utils.print_message(self.utils.logtype.ERROR,
                                             "Error generating bootimage:",
                                             k)
                    generate_img = False

            if generate_img:
                continue

            # if the image was not generated we need to delete previously
            # generated files
            with self.utils.cd(directory):
                if 'result_files' not in bootimages[k].keys():
                    continue
                for f in bootimages[k]['result_files']:
                    if not os.path.isfile(f):
                        continue

                    try:
                        os.remove(f)
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Failed to remove file",
                                                 f, ":", str(exc))

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
                if self.targets[t]["history"]:
                    current_target_line += " \w history"

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
                if self.is_copyfiles_default(b):
                    binary_lines_a.append("Custom binaries used.")
                    for bf in self.binaries[b]["copy_files"]:
                        is_def = " (default)" if not os.path.isabs(bf[1]) \
                                              else ""
                        binary_lines_a.append(bf[0] + " : " + bf[1]+is_def)

        binary_lines = "Binaries:" + line_sep + node_sep.join(binary_lines_a)

        # construct the final summary
        summary = []

        summary.append(device_lines)
        summary.append(target_lines)
        if not self.fetch_only_run():
            summary.append(binary_lines)

        return (line_sep+"\n").join(summary)
