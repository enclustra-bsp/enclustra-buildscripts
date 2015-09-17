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
    def __init__(self, root_path, master_repo_path, config_path, ini_files,
                 target_name, debug_calls, utils):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.root_path = root_path
        self.master_repo_path = master_repo_path
        self.config_path = config_path
        self.config.read(ini_files)
        self.toolchains = []
        self.targets = dict()
        self.binaries = dict()
        self.bootimages = dict()
        self.parse_init_file()
        self.target_name = str(target_name)
        binary_keys = self.binaries.keys()
        self.debug_calls = debug_calls
        self.utils = utils

    def save_config(self, filename):
        for t in self.targets:
            key = t + "-options"
            if self.config.has_section(key) is False:
                self.config.add_section(key)

            self.config.set(key, "fetch", str(self.targets[t]["fetch"]))
            self.config.set(key, "fetch_history",
                            str(self.targets[t]["history"]))

            self.config.set(key, "build", str(self.targets[t]["build"]))

            subtargets = []
            for s in self.targets[t]["parallelbuild_commands"]:
                if s["enabled"] is False:
                    continue
                st = s["name"].split(" ")
                if len (st)< 1:
                    continue
                subtargets.append(st[-1])

            self.config.set(key, "build_steps", ",".join(subtargets))

            if self.config.has_section("binaries") is True:
                for b in self.config["binaries"]:
                    self.config.set("binaries", b,
                                    str(self.binaries[b]["chosen"]))

            # set project name
            if self.config.has_section("project") is False:
                self.config.add_section("project")

            self.config.set("project", "name", self.get_name())

            relative_path = self.config_path[len(self.root_path):]

            self.config.set("project", "path", relative_path)

        history_path = self.root_path + "/.history/"
        if not os.path.exists(history_path):
            os.makedirs(history_path)

        try:
            history_fname = history_path + filename + ".ini"

            cfgfile = open(history_fname, 'w')
            self.config.write(cfgfile)
            self.utils.print_message(self.utils.logtype.INFO,
                                     "History file saved.")
        except:
            self.utils.print_message(self.utils.logtype.WARNING,
                                     "Failed to save history file.")

    def get_name(self):
        return self.target_name

    def get_fullname(self):
        for b in self.binaries:
            if self.binaries[b]['chosen'] is False:
                continue
            return self.get_name() + "_" + self.binaries[b]['shortname']
        return self.get_name()

    def get_out_dir(self, root_path):
        return root_path + "/" + "out_" + self.get_fullname()

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
            target_fetch = True
            target_fetch_history = False
            target_build = True
            target_active = self.config.getboolean('targets', target)
            target_repository = self.config[target]['repository']

            if self.config.has_option(target, "branch") is True:
                target_branch = self.config[target]["branch"]

            if self.config.has_option(target, "disables") is True:
                target_disable = self.config[target]["disables"]
            if self.config.has_section(target + "-help") is True:
                if self.config.has_option(target + "-help",
                                          "description") is True:
                    target_help = self.config[target + "-help"]["description"]
                if self.config.has_option(target + "-help",
                                          "box") is True:
                    target_helpbox = self.config[target + "-help"]["box"]

            if self.config.has_section(target + "-build") is True:
                for command in self.config[target + "-build"]:
                    target_build_commands.append(self.config[str(target) +
                                                 "-build"][command])

            key = target + "-options"
            if self.config.has_section(target + "-parallelbuild") is True:
                for command in self.config[target + "-parallelbuild"]:
                    subtarget = dict()
                    subtarget['name'] = target + " " + command
                    subtarget['cmd'] = self.config[str(target) +
                                                   "-parallelbuild"][command]

                    skey = "build_steps"

                    subtarget['enabled'] = False

                    if self.config.has_section(key) is False:
                        subtarget['enabled'] = True
                        target_parallelbuild_commands.append(subtarget)
                        continue
                    if self.config.has_option(key, skey) is False:
                        subtarget['enabled'] = True
                        target_parallelbuild_commands.append(subtarget)
                        continue

                    subtarget['enabled'] = command in self.config[key][skey]

                    target_parallelbuild_commands.append(subtarget)

            if self.config.has_section(key) is True:
                if self.config.has_option(key, "fetch"):
                    target_fetch = self.config.getboolean(key, "fetch")
                if self.config.has_option(key, "fetch_history"):
                    target_fetch_history = \
                        self.config.getboolean(key, "fetch_history")

                if self.config.has_option(key, "build"):
                    target_build = self.config.getboolean(key, "build")

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
            target_descriptor.update([("history", target_fetch_history)])
            target_descriptor.update([("build", target_build)])
            target_descriptor.update([("disable_build", False)])
            target_descriptor.update([("build_error", False)])
            target_descriptor.update([("repository", target_repository)])
            target_descriptor.update([("branch", target_branch)])
            target_descriptor.update([("patches", target_patches)])
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
                if self.config.has_option(binary, "helpbox"):
                    helpbox = self.config[binary]["helpbox"]
                else:
                    helpbox = None

                for copyfile in self.config[binary+"-copyfiles"]:
                    binary_copyfiles.append([copyfile,
                                             self.config[binary + "-copyfiles"]
                                             [copyfile]])

                binary_descriptor.update([("default", is_default)])
                binary_descriptor.update([("description", description)])
                binary_descriptor.update([("helpbox", helpbox)])
                binary_descriptor.update([("uri", download_uri)])
                binary_descriptor.update([("unpack", unpack)])
                binary_descriptor.update([("redownload", redownload)])
                binary_descriptor.update([("shortname", shortname)])
                binary_descriptor.update([("copy_files", binary_copyfiles)])
                binary_descriptor.update([("chosen", False)])

                self.binaries.update([(binary, binary_descriptor)])

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
                    for f in self.config[k +'-result-files']:
                        if self.config.getboolean(k + '-result-files', f):
                            result_files.append(f)
                self.bootimages[k]['files'] = files
                self.bootimages[k]['result_files'] = result_files

    def get_target_helpbox(self, target):
        return self.targets[target]["helpbox"]

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
            binaries.append([(self.binaries[binary])["description"], ""])

        return binaries

    def get_default_binary(self):
        for binary in self.binaries:
            if self.binaries[binary]["default"]:
                return binary

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

    def get_build_opts(self):
        build_opts = []

        for target in self.targets:
            if (self.targets[target])["build"] is False:
                continue
            for subt in (self.targets[target])["parallelbuild_commands"]:
                build_opts.append([subt['name'], "", subt['enabled']])
        return build_opts

    def get_subtargets(self, target):
        build_opts = []

        if (self.targets[target])["build"] is True:
            for subt in (self.targets[target])["parallelbuild_commands"]:
                build_opts.append(subt['name'])

        return build_opts

    def validate_subtargets(self, subtargets):
        invalid = []
        invalid.extend(subtargets)
        for target in self.targets:
            for c in (self.targets[target])["parallelbuild_commands"]:
                if c['name'] in subtargets:
                    invalid.remove(c['name'])
        return invalid

    def set_build_opts(self, build_opts):
        for target in self.targets:
            if (self.targets[target])["build"] is False:
                continue
            for c in (self.targets[target])["parallelbuild_commands"]:
                c['enabled'] = c['name'] in build_opts

    def get_fetch(self):
        fetch = []
        for target in self.targets:
            help_msg = "Fetch " + self.targets[target]["help"]
            fetch.append([target, "", (self.targets[target])["fetch"],
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
            help_msg = "Build " + self.targets[target]["help"]
            if self.targets[target]["disable"] is not None:
                help_msg += " Choosing this target will disable building " +\
                            "of the " + self.targets[target]["disable"] + \
                            " target."
            build.append([target, "", (self.targets[target])["build"],
                         help_msg])
        return build

    def set_build(self, build):
        for target in build:
            if target not in self.targets.keys():
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
            if (self.targets[target])["disable_fetch"] is True:
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

            # Switch branch if specified
            if (self.targets[target])["branch"] is not None:
                call = "git fetch " + depth + " origin " + \
                       (self.targets[target])["branch"]

                repo_dir = self.master_repo_path + "/" + \
                           str((self.targets[target])["repository"])

                with self.utils.cd(repo_dir):
                    sp = self.utils.call_tool(call)
                call = "git checkout FETCH_HEAD"
                if sp == 0:
                    with self.utils.cd(repo_dir):
                        sp = self.utils.call_tool(call)
            if sp != 0:
                # if fetching failed unmark this target from building
                (self.targets[target])["build"] = False
                self.utils.print_message(self.utils.logtype.WARNING,
                                         "Fetching for", target, "failed")
                continue

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
        for target in self.targets:
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

            with self.utils.cd((self.master_repo_path + "/" +
                               (self.targets[target])["repository"])):
                # store PATH
                orig_path = os.environ["PATH"]
                toolchain_path = ""
                for path in toolchains_paths:
                    toolchain_path += str(path) + ":"
                os.environ["PATH"] = toolchain_path + orig_path

                # build parallel targets
                for subt in (self.targets[target])["parallelbuild_commands"]:
                    if subt['enabled']:
                        self.call_build_tool(subt['cmd'], target, nthreads)

                # build targets
                for command in (self.targets[target])["build_commands"]:
                    self.call_build_tool(command, target, 0)

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
            call = "wget "
            if self.binaries[binary]["redownload"] is False:
                call = call + "-N "
            elif os.path.isfile(download_path + "/" + binary_file):
                os.remove(download_path + "/" + binary_file)
            call = call + self.binaries[binary]["uri"]
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
                        # the downloaded file is corrupted, delete it
                        shutil.rmtree(download_path)

                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Error while unpacking",
                                                 binary, "binary:", exc,
                                                 "- deleting.")
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
                        self.utils.print_message(self.utils.logtype.INFO,
                                                 "Copying ./" + os.path.relpath(src) +
                                                 " to ./" + os.path.relpath(dst))
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.ERROR,
                                                 "Error while copying file",
                                                 src, ":", str(exc))

            # delete any existing previous products of failed builds
            if (self.targets[target])["build_error"] is True:
                for outfile in (self.targets[target])["copy_files"]:
                    file_path = dst_path + "/" + outfile[0]
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as exc:
                        self.utils.print_message(self.utils.logtype.WARNING,
                                                 "Error while deleting file",
                                                 file_path, ":", str(exc))

        # there are some binaries
        if bool(self.binaries) and not self.fetch_only_run():
            self.utils.print_message(self.utils.logtype.INFO,
                                     "Copying binaries")
        # copy binaries
        for binary in self.binaries:
            if 'path' not in self.binaries[binary].keys():
                continue
            for outfile in (self.binaries[binary])["copy_files"]:
                src = self.binaries[binary]["path"] + "/" + outfile[1]
                dst = dst_path + "/" + outfile[0]
                try:
                    shutil.copyfile(src, dst)
                    self.utils.print_message(self.utils.logtype.INFO,
                                                 "Copying ./" + os.path.relpath(src) +
                                                 " to ./" + os.path.relpath(dst))
                except Exception as exc:
                    self.utils.print_message(self.utils.logtype.WARNING,
                                             "Error while copying file",
                                             src, ":", str(exc))

    def do_generate_image(self, directory, toolchains_paths):
        bootimages = self.get_bootimages()

        for k in bootimages.keys():
            generate_img = True
            # there is no bootimage to build
            if 'cmd' not in bootimages[k].keys():
                return

            # check if every required file is accessible
            with self.utils.cd(directory):
                for f in bootimages[k]['files']:
                    if not os.path.isfile(f):
                        generate_img = False
                        break

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

        binary_lines = "Binaries:" + line_sep + node_sep.join(binary_lines_a)

        # construct the final summary
        summary = []

        summary.append(device_lines)
        summary.append(target_lines)
        if not self.fetch_only_run():
            summary.append(binary_lines)

        return (line_sep+"\n").join(summary)
