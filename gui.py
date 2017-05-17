#! /usr/bin/env python2
# -*- coding: utf-8 -*-

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

# \file build.py
# \brief Enclustra Build Environment gui class
# \author Karol Gugala <kgugala@antmicro.com>
# \date 2015-07-03
#
# \copyright Copyright (c) 2015-2017 Enclustra GmbH, Switzerland. All rights reserved.
# \licence This code is released under the Modified BSD licence.

import os
import sys

version = sys.version_info
if version < (3, 0, 0):
    import dialog2 as dialog
else:
    import dialog3 as dialog


class Gui:
    def __init__(self, workdir):
        self.workdir = workdir
        self.basedir = workdir
        self.dialog = dialog.Dialog(dialog="dialog")
        self.top = True
        self.bottom = False
        self.inifiles = list()
        if os.path.isfile(workdir + "/build.ini"):
            self.inifiles.append(workdir + "/build.ini")
        self.new_config_tag = "New configuration..."

    def show_welcome_screen(self, msg):
        self.dialog.msgbox(msg, width=80)

    def show_previous_configs(self, configs):
        configs = [(self.new_config_tag, "")] + configs

        width = 80
        for text in configs:
            if len(text) + 16 > width:
                width = len(text) + 16
        return self.dialog.menu("Choose configuration",
                                choices=configs,
                                width=width,
                                cancel_label="Exit")

    def step_in(self, directory):
        if self.check_bottom_level() is False:
            self.workdir += "/"+directory
            if os.path.isfile(self.workdir + "/build.ini") is True:
                self.inifiles.append(self.workdir + "/build.ini")
        self.top = self.check_top_level()
        self.bottom = self.check_bottom_level()

    def step_out(self):
        if self.check_top_level() is False:
            # if there is a 'build.ini' in this folder we need to remove
            # it from inifiles list
            if os.path.isfile(self.workdir + "/build.ini"):
                self.inifiles.pop()
            self.workdir = os.path.dirname(self.workdir)
        self.top = self.check_top_level()
        self.bottom = self.check_bottom_level()

    def get_workdir(self):
        return self.workdir

    def get_inifiles(self):
        return self.inifiles

    def list_directories(self, workdir):
        # list directories only
        dirs = [name for name in os.listdir(workdir) if
                os.path.isdir(os.path.join(workdir, name))]
        return dirs

    def get_choices(self):
        description = "Choose"
        choices = []
        # get the description
        try:
            desc_file = open(self.workdir + "/description", "r")
            desc = desc_file.read()
            desc_file.close()
            description = desc
        except:
            # if there was exception during description reading we use
            # default one
            pass
        # get the choices
        try:
            choices_dirs = self.list_directories(self.workdir)
        except:
            return None
        for choice in choices_dirs:
            choices.append([choice, ""])
        if len(choices) == 0:
            return None
        else:
            return (description, choices)

    def show_level_menu(self, exit_label=False):
        tagmap = dict()
        try:
            description, choices = self.get_choices()
        except:
            self.dialog.msgbox("Error while searching for available choices!")
            return "exit"

        # substitute underscores with spaces but keep the key for later use
        for choice in choices:
            tagmap[choice[0].replace("_", " ")] = choice[0]
            choice[0] = choice[0].replace("_", " ")

        code, tag = self.dialog.menu(description, choices=choices,
                                     cancel_label="Exit" if exit_label
                                     else "Back")
        if code == self.dialog.OK:
            # restore the original key from before underscore substitution
            tag = tagmap[tag]
            self.step_in(tag)
            if self.bottom is True:
                return "done"
        else:
            if exit_label is True:
                return "exit"
            elif self.top is True:
                return "back"
            self.step_out()
        return "ok"

    def get_target_name(self):
        target_rel_path = os.path.relpath(self.workdir, self.basedir)
        target_name = target_rel_path.replace("/", "_").replace(" ", "_")
        return target_name

    def check_bottom_level(self):
        # if there are no directories we assume this is a bottom level
        try:
            dirs = self.list_directories(self.workdir)
        except:
            return True
        return not bool(len(dirs))

    def check_top_level(self):
        return self.workdir == self.basedir

    def show_fetch_menu(self, menu_items):
        if len(menu_items) != 0:
            return self.dialog.checklist("Which targets do you want to fetch?",
                                         choices=menu_items, extra_button=True,
                                         extra_label="Advanced",
                                         item_help=True,
                                         help_button=True,
                                         help_tags=True,
                                         cancel_label="Back")
        else:
            return self.dialog.msgbox("No target marked to fetch found!")

    def show_binaries_menu(self, menu_items):
        if len(menu_items) != 0:
            for m in menu_items:
                m.append("* custom binary set | + modified")
            return self.dialog.menu("Choose the device option.",
                                    choices=menu_items,
                                    extra_button=True,
                                    extra_label="Customize",
                                    help_button=True,
                                    help_tags=True,
                                    cancel_label="Back",
                                    item_help=True,
                                    )
        else:
            return self.dialog.msgbox("No device options found!")

    def show_custom_files_menu(self, files):
        menu_options = []
        for f in files:
            if files[f]["chosen"]:
                try:
                    for outfile in (files[f])["copy_files"]:
                        if os.path.isabs(outfile[1]):
                            menu_options.append(outfile)
                        else:
                            menu_options.append([outfile[0],
                                                outfile[1]+" (default path)"])
                except TypeError:
                    return self.dialog.msgbox("No binary files found."), ""
        return self.dialog.menu("Setup custom paths for binaries.",
                                choices=menu_options,
                                extra_button=True,
                                extra_label="Edit",
                                help_button=True,
                                help_label="Default",
                                cancel_label="Reset",
                                width=0)

    def show_custom_binary_sel(self, bin_file, src_path):
        return self.dialog.fselect(src_path,
                                   height=10,
                                   width=60,
                                   title="Select location for file "+bin_file)

    def show_fetch_opts_menu(self, menu_items):
        if len(menu_items) != 0:
            return self.dialog.checklist("Fetch targets with history?",
                                         choices=menu_items,
                                         cancel_label="Back")
        else:
            return self.dialog.msgbox("No target marked to fetch found!")

    def show_build_opts_menu(self, menu_items):
        if len(menu_items) != 0:
            return self.dialog.checklist("Enable specific building steps",
                                         choices=menu_items,
                                         cancel_label="Back")
        else:
            return self.dialog.msgbox("No target marked to build found!")

    def show_build_menu(self, menu_items):
        if len(menu_items) != 0:
            return self.dialog.checklist("Which targets do you want to build?",
                                         choices=menu_items,
                                         item_help=True,
                                         help_button=True,
                                         help_tags=True,
                                         cancel_label="Back")
        else:
            return self.dialog.msgbox("No target marked to build found!")

    def show_help(self, target, help_msg):
        if help_msg:
            msg = help_msg
        else:
            msg = "No help message for " + target
        return self.dialog.msgbox(msg, 15, 60)

    def show_warning(self, msg):
        msg = "WARNING\n" + msg
        return self.dialog.msgbox(msg, 15, 60)

    def show_summary_menu(self, summary, used_previous_config):
        # question shown to user
        w_question = "Please verify all the chosen parameters"
        w_text = "%s\n\n%s" % (w_question, summary)

        # calculate window size
        w_height = w_text.count("\n") + 6  # num of lines + 6 for frame/buttons
        w_width = len((max(w_text.split("\n"), key=len))) + 4  # 4 is the frame

        if used_previous_config is True:
            back_label = "Customize"
        else:
            back_label = "Back"

        return self.dialog.yesno(w_text, w_height, w_width,
                                 yes_label="Proceed", no_label=back_label)

    def show_history_fname_dialog(self, def_name):
        width = len(def_name) + 10
        if width < 80:
            width = 80

        return self.dialog.inputbox("Save configuration file...",
                                    init=def_name, width=width,
                                    extra_button=True,
                                    extra_label="Advanced",
                                    cancel_label="Build without saving")

    def show_project_menu(self):
        msg = "If you intend to modify the sources, enable project mode"
        return self.dialog.checklist(msg,
                                     choices=[("enable", "", False)])
