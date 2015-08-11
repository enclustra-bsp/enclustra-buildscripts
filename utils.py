#! /usr/bin/env python2

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

# \file utils.py
# \brief Enclustra Build Environment utils class
# \author Karol Gugala <kgugala@antmicro.com>
# \date 2015-07-03
#
# \copyright Copyright (c) 2015 Enclustra GmbH, Switzerland. All rights reserved.
# \licence This code is released under the Modified BSD licence.


import subprocess
import os
import shutil
import errno
import archive
import re
import shlex
import sys
import signal


class Utils:
    class logtype:
        DEFAULT = 0
        INFO = 1
        OK = 2
        WARNING = 3
        ERROR = 4

    class bcolors:
        HEADER = '\033[35m'
        INFO = '\033[34m'
        OK = '\033[32m'
        WARNING = '\033[33m'
        ERROR = '\033[31m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'

    def __init__(self):
        self.debug = False
        self.log_file = None
        self.quiet_mode = False
        self.break_on_error = False

    def set_debug_calls(self, value):
        self.debug = value

    # Log file has to be opened outside
    def set_log_file(self, log_file):
        self.log_file = log_file

    def set_quiet_mode(self, mode):
        self.quiet_mode = mode

    def set_break_on_error(self, mode):
        self.break_on_error = mode

    def print_message(self, loglevel, *args):
        if loglevel == self.logtype.INFO:
            textcolor = self.bcolors.BOLD + self.bcolors.INFO + "INFO: "
        elif loglevel == self.logtype.OK:
            textcolor = self.bcolors.BOLD + self.bcolors.OK
        elif loglevel == self.logtype.WARNING:
            textcolor = self.bcolors.BOLD + self.bcolors.WARNING + "WARNING: "
        elif loglevel == self.logtype.ERROR:
            textcolor = self.bcolors.BOLD + self.bcolors.ERROR + "ERROR: "
        else:
            textcolor = ""

        if self.log_file is not None:
            self.log_file.write(" ".join(str(i) for i in args) + '\n')
            self.log_file.flush()

        print(textcolor + " ".join(str(i) for i in args) + self.bcolors.ENDC)
        
        if loglevel == self.logtype.ERROR:
            print('\n')
            if self.break_on_error is True:
                print("Break on error is set. Terminating run!")
                sys.exit(1)

    def call_tool(self, call):
        if self.debug is True:
            print(self.bcolors.HEADER + "+" + call + self.bcolors.ENDC)
        proc = subprocess.Popen(shlex.split(call), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        for line in proc.stdout:
            if self.quiet_mode is False:
                sys.stdout.write(line)
            if self.log_file is not None:
                self.log_file.write(line)
                self.log_file.flush()
        proc.wait()
        return proc.returncode

    def get_git_revision(self):
        call = "git rev-parse --short HEAD"
        try:
            revision = subprocess.check_output(shlex.split(call))
        except:
            revision = "unknown"
        return revision

    def run_post_script(self, state, target, boardpath, master_repo_path):
        script = target["post"+state]
        src = boardpath + "/" + script
        dst = master_repo_path + "/" + target["repository"]
        try:
            shutil.copyfile(src, dst+"/"+script)
        except:
            self.print_message(self.logtype.ERROR, "Error copying file", src,
                               "to", dst)
            raise IOError
        with self.cd(dst):
            try:
                call = "bash "+script
                sp = self.call_tool(call)
            except:
                sp = -1
            if sp != 0:
                self.print_message(self.logtype.ERROR, "Post" + state,
                                   "script", script, "failed")
                raise IOError

    def register_toolchain(self, toolchains, name, config, remote):
        descriptor = dict()
        descriptor.update([("remote", remote)])
        if remote is True:
            try:
                descriptor.update([("server", config[name]["server"])])
                descriptor.update([("path", config[name]["path"])])
            except:
                # catch all the exceptions print warning and return
                self.print_message(self.logtype.WARNING,
                                   "Warning: Failed to register toolchain",
                                   name)
                return
        toolchains.update([(name, descriptor)])

    def acquire_toolchains(self, required, registered, path, debug_calls):
        return_paths = []
        for toolchain in required:
            if toolchain in registered:
                # if toolchain is registered as 'local' return empty string
                if registered[toolchain]["remote"] is False:
                    return_paths.append("")

                toolchain_location = registered[toolchain]["server"]

                with self.cd(path + "/bin"):
                    if os.path.isfile(os.path.basename(toolchain_location)) is False:
                        call = "wget " + toolchain_location
                        if self.call_tool(call) != 0:
                            self.print_message(self.logtype.ERROR,
                                               "Error while downloading toolchain")
                            raise NameError("Required toolchains: " +
                                            ", ".join(required))
                        try:
                            a = archive.Archive(os.path.basename(toolchain_location))
                            a.extract()
                        except Exception as ext:
                            # the downloaded file is corrupted, delete it
                            os.remove(os.path.basename(toolchain_location))

                            self.print_message(self.logtype.ERROR,
                                               "Error while unpacking",
                                               os.path.basename(toolchain_location),
                                               "toolchain.",
                                               str(ext),
                                               "- deleting.")

                            raise NameError("Required toolchains: " +
                                            ", ".join(required))

                return_paths.append(path + "/bin/" + registered[toolchain]["path"])
            else:
                self.print_message(self.logtype.ERROR, required,
                                   "toolchain is not registered")
                raise NameError("Required toolchains: " + ", ".join(required))
        return return_paths

    def tryint(self, x):
        try:
            return int(x)
        except ValueError:
            return x

    def splittedname(self, s):
        return tuple(self.tryint(x) for x in re.split('([0-9]+)', s))

    def check_tool(self, command, option, version_location, minimal_version):
        try:
            stdoutdata = subprocess.check_output([command, option],
                                                 stderr=subprocess.PIPE)
        except:
            return False
        local = self.splittedname(str(stdoutdata).split()[version_location - 1])
        minimal = self.splittedname(minimal_version)
        return local >= minimal

    def list_devices(self, entry_point=""):
        print(str("List of available devices:"))
        for root, dirs, files in os.walk("targets/" + entry_point):
            if root == "targets" + entry_point:
                continue
            if len(dirs) == 0:
                # remove the leading targets catalog
                root = root.replace("targets/", '')
                # make the spaces copy-pasteable
                print("\"" + root + "\"")

    class cd:
        """Context manager for changing the current working directory"""
        def __init__(self, newPath):
            self.newPath = os.path.expanduser(newPath)

        def __enter__(self):
            self.savedPath = os.getcwd()
            os.chdir(self.newPath)

        def __exit__(self, etype, value, traceback):
            os.chdir(self.savedPath)

    def mkdir_p(self, path):
        try:
            os.makedirs(path)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise

    def init_sigint_handler(self):
        self.sigint_orig_handler = signal.getsignal(signal.SIGINT)

        def signal_handler(signal, frame):
            #subprocess.call("clear")
            self.print_message(self.logtype.INFO,
                               "Received SIGINT - aborting.")
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)

    def deinit_sigint_handler(self):
        if self.sigint_orig_handler is not None:
            signal.signal(signal.SIGINT, self.sigint_orig_handler)
