# Copyright 2014-2016 The Meson development team

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys, os
import pickle
import argparse
from . import coredata, mesonlib

parser = argparse.ArgumentParser()

parser.add_argument('-D', action='append', default=[], dest='sets',
                    help='Set an option to the given value.')
parser.add_argument('directory', nargs='*')
parser.add_argument('--clearcache', action='store_true', default=False,
                    help='Clear cached state (e.g. found dependencies)')
parser.add_argument('--dump', action='store', nargs='?', default=False,
                    help='Dump current configuration (optional: filename to write it in)')
parser.add_argument('--tui', action='store_true', default=False,
                    help='Open TUI configuration menu')

class ConfException(mesonlib.MesonException):
    pass

class Conf:
    def __init__(self, build_dir):
        self.build_dir = build_dir
        self.coredata_file = os.path.join(build_dir, 'meson-private/coredata.dat')
        self.build_file = os.path.join(build_dir, 'meson-private/build.dat')
        if not os.path.isfile(self.coredata_file) or not os.path.isfile(self.build_file):
            raise ConfException('Directory %s does not seem to be a Meson build directory.' % build_dir)
        with open(self.coredata_file, 'rb') as f:
            self.coredata = pickle.load(f)
        with open(self.build_file, 'rb') as f:
            self.build = pickle.load(f)
        if self.coredata.version != coredata.version:
            raise ConfException('Version mismatch (%s vs %s)' %
                                (coredata.version, self.coredata.version))

    def clear_cache(self):
        self.coredata.deps = {}

    def save(self):
        # Only called if something has changed so overwrite unconditionally.
        with open(self.coredata_file, 'wb') as f:
            pickle.dump(self.coredata, f)
        # We don't write the build file because any changes to it
        # are erased when Meson is executed the next time, i.e. whne
        # Ninja is run.

    def print_aligned(self, arr):
        if not arr:
            return
        titles = {'name': 'Option', 'descr': 'Description', 'value': 'Current Value', 'choices': 'Possible Values'}
        len_name = longest_name = len(titles['name'])
        len_descr = longest_descr = len(titles['descr'])
        len_value = longest_value = len(titles['value'])
        longest_choices = 0 # not printed if we don't get any optional values

        # calculate the max length of each
        for x in arr:
            name = x['name']
            descr = x['descr']
            value = x['value'] if isinstance(x['value'], str) else str(x['value']).lower()
            choices = ''
            if isinstance(x['choices'], list):
                if x['choices']:
                    x['choices'] = [s if isinstance(s, str) else str(s).lower() for s in x['choices']]
                    choices = '[%s]' % ', '.join(map(str, x['choices']))
            elif x['choices']:
                choices = x['choices'] if isinstance(x['choices'], str) else str(x['choices']).lower()

            longest_name = max(longest_name, len(name))
            longest_descr = max(longest_descr, len(descr))
            longest_value = max(longest_value, len(value))
            longest_choices = max(longest_choices, len(choices))

            # update possible non strings
            x['value'] = value
            x['choices'] = choices

        # prints header
        namepad = ' ' * (longest_name - len_name)
        valuepad = ' ' * (longest_value - len_value)
        if longest_choices:
            len_choices = len(titles['choices'])
            longest_choices = max(longest_choices, len_choices)
            choicepad = ' ' * (longest_choices - len_choices)
            print('  %s%s %s%s %s%s %s' % (titles['name'], namepad, titles['value'], valuepad, titles['choices'], choicepad, titles['descr']))
            print('  %s%s %s%s %s%s %s' % ('-' * len_name, namepad, '-' * len_value, valuepad, '-' * len_choices, choicepad, '-' * len_descr))
        else:
            print('  %s%s %s%s %s' % (titles['name'], namepad, titles['value'], valuepad, titles['descr']))
            print('  %s%s %s%s %s' % ('-' * len_name, namepad, '-' * len_value, valuepad, '-' * len_descr))

        # print values
        for i in arr:
            name = i['name']
            descr = i['descr']
            value = i['value']
            choices = i['choices']

            namepad = ' ' * (longest_name - len(name))
            valuepad = ' ' * (longest_value - len(value))
            if longest_choices:
                choicespad = ' ' * (longest_choices - len(choices))
                f = '  %s%s %s%s %s%s %s' % (name, namepad, value, valuepad, choices, choicespad, descr)
            else:
                f = '  %s%s %s%s %s' % (name, namepad, value, valuepad, descr)

            print(f)

    def set_options(self, options):
        for o in options:
            if '=' not in o:
                raise ConfException('Value "%s" not of type "a=b".' % o)
            (k, v) = o.split('=', 1)
            self.set_option(k, v)

    def set_option(self, k, v):
            if coredata.is_builtin_option(k):
                self.coredata.set_builtin_option(k, v)
            elif k in self.coredata.backend_options:
                tgt = self.coredata.backend_options[k]
                tgt.set_value(v)
            elif k in self.coredata.user_options:
                tgt = self.coredata.user_options[k]
                tgt.set_value(v)
            elif k in self.coredata.compiler_options:
                tgt = self.coredata.compiler_options[k]
                tgt.set_value(v)
            elif k in self.coredata.base_options:
                tgt = self.coredata.base_options[k]
                tgt.set_value(v)
            elif k.endswith('_link_args'):
                lang = k[:-10]
                if lang not in self.coredata.external_link_args:
                    raise ConfException('Unknown language %s in linkargs.' % lang)
                # TODO, currently split on spaces, make it so that user
                # can pass in an array string.
                newvalue = v.split()
                self.coredata.external_link_args[lang] = newvalue
            elif k.endswith('_args'):
                lang = k[:-5]
                if lang not in self.coredata.external_args:
                    raise ConfException('Unknown language %s in compile args' % lang)
                # TODO same fix as above
                newvalue = v.split()
                self.coredata.external_args[lang] = newvalue
            else:
                raise ConfException('Unknown option %s.' % k)

    def get_core_options(self):
        carr = []
        for key in ['buildtype', 'warning_level', 'werror', 'strip', 'unity', 'default_library']:
            carr.append({'name': key,
                         'descr': coredata.get_builtin_option_description(key),
                         'value': self.coredata.get_builtin_option(key),
                         'choices': coredata.get_builtin_option_choices(key)})
        return carr

    def get_backend_options(self):
        bearr = []
        bekeys = sorted(self.coredata.backend_options.keys())
        if not bekeys:
            return bearr
        for k in bekeys:
            o = self.coredata.backend_options[k]
            bearr.append({'name': k, 'descr': o.description, 'value': o.value, 'choices': ''})
        return bearr

    def get_base_options(self):
        obarr = []
        okeys = sorted(self.coredata.base_options.keys())
        if not okeys:
            return coarr
        for k in okeys:
            o = self.coredata.base_options[k]
            obarr.append({'name': k, 'descr': o.description, 'value': o.value, 'choices': ''})
        return obarr

    def get_compiler_args(self):
        cargs = []
        for (lang, args) in self.coredata.external_args.items():
            cargs.append({'name': lang + '_args', 'value': args})
        return cargs

    def get_linker_args(self):
        largs = []
        for (lang, args) in self.coredata.external_link_args.items():
            largs.append({'name': lang + '_link_args', 'value': args})
        return largs

    def get_compiler_options(self):
        coarr = []
        okeys = sorted(self.coredata.compiler_options.keys())
        if not okeys:
            return coarr
        for k in okeys:
            o = self.coredata.compiler_options[k]
            coarr.append({'name': k, 'descr': o.description, 'value': o.value, 'choices': ''})
        return coarr

    def get_directories_options(self):
        parr = []
        for key in ['prefix',
                    'libdir',
                    'libexecdir',
                    'bindir',
                    'sbindir',
                    'includedir',
                    'datadir',
                    'mandir',
                    'infodir',
                    'localedir',
                    'sysconfdir',
                    'localstatedir',
                    'sharedstatedir',
                    ]:
            parr.append({'name': key,
                         'descr': coredata.get_builtin_option_description(key),
                         'value': self.coredata.get_builtin_option(key),
                         'choices': coredata.get_builtin_option_choices(key)})
        return parr

    def get_project_options(self):
        options = self.coredata.user_options
        optarr = []
        if not options:
            return optarr
        keys = list(options.keys())
        keys.sort()
        for key in keys:
            opt = options[key]
            if (opt.choices is None) or (not opt.choices):
                # Zero length list or string
                choices = ''
            else:
                # A non zero length list or string, convert to string
                choices = str(opt.choices)
            optarr.append({'name': key,
                           'descr': opt.description,
                           'value': opt.value,
                           'choices': choices})
        return optarr

    def get_testing_options(self):
        tarr = []
        for key in ['stdsplit', 'errorlogs']:
            tarr.append({'name': key,
                         'descr': coredata.get_builtin_option_description(key),
                         'value': self.coredata.get_builtin_option(key),
                         'choices': coredata.get_builtin_option_choices(key)})
        return tarr

    def print_conf(self):
        print('Core properties:')
        print('  Source dir', self.build.environment.source_dir)
        print('  Build dir ', self.build.environment.build_dir)
        print('')
        print('Core options:')
        carr = self.get_core_options()
        self.print_aligned(carr)
        print('')
        bearr = self.get_backend_options()
        if not bearr:
            print('  No backend options\n')
        else:
            self.print_aligned(bearr)
        print('')
        print('Base options:')
        obarr = self.get_base_options()
        if not obarr:
            print('  No base options\n')
        else:
            self.print_aligned(obarr)
        print('')
        print('Compiler arguments:')
        for lang in self.get_compiler_args():
            print('  ' + lang['name'], str(lang['value']))
        print('')
        print('Linker args:')
        for lang in self.get_linker_args():
            print('  ' + lang['name'], str(lang['value']))
        print('')
        print('Compiler options:')
        coarr = self.get_compiler_options()
        if not coarr:
            print('  No compiler options\n')
        else:
            self.print_aligned(coarr)
        print('')
        print('Directories:')
        parr = self.get_directories_options()
        self.print_aligned(parr)
        print('')
        print('Project options:')
        optarr = self.get_project_options()
        if not optarr:
            print('  This project does not have any options')
        else:
            self.print_aligned(optarr)
        print('')
        print('Testing options:')
        tarr = self.get_testing_options()
        self.print_aligned(tarr)

    def dump_conf(self, outfilename):
        options = {
                    'core': self.get_core_options(),
                    'backend': self.get_backend_options(),
                    'base': self.get_base_options(),
                    'compiler_args': self.get_compiler_args(),
                    'linker_args': self.get_linker_args(),
                    'compiler_options': self.get_compiler_options(),
                    'directories': self.get_directories_options(),
                    'project': self.get_base_options(),
                    'testing': self.get_testing_options(),
                  }
        if outfilename:
            outfile = open(outfilename, 'w')
        else:
            outfile = sys.stdout
        for group in options:
            for option in options[group]:
                #TODO
                # if option['value'] == option['default']:
                #   continue
                optname = option['name']
                optvalue = option['value']
                if isinstance(optvalue, list):
                    optvalue = ' '.join(optvalue)
                outfile.write('-D{}="{}" '.format(optname, optvalue))
        outfile.close()

    def show_tui(self):
        import curses

        legend = {
                '↓/↑/j/k': 'select option',
                'pgup/pgdown': 'scroll description',
                'enter': 'edit/save option',
                #'delete': 'reset option to default value', #TODO: figure out how to get the default value
                'q': 'quit'
                }
        details_minheight = 0
        legend_height = 0
        list_maxheight = 0

        def tui_draw_legend(win_legend):
            win_legend.clear()
            line = 0
            for key in legend:
                win_legend.addstr(line,0, '[' + key + '] ' + legend[key]);
                line+=1
            win_legend.refresh()

        def tui_draw_details(pad_details, option):
            #TODO
            # - option name (type, default, choices)
            # - option description (min 2 lines, expand if needed)
            #pad_details.refresh()
            return

        def tui_draw_options(pad_options, option_index, options_maxheight):
            #TODO
            # - groups (same as `meson configure`)
            # - each line has option & current value
            #pad_options.refresh()
            return

        def tui_set_option(name, value, win_error):
            from .mesonlib import MesonException
            try:
                self.set_option(name, value)
            except MesonException as e:
                tui_error(win_error, str(e))
                pass

        def tui_error(win_error, msg):
            win_error.clear()
            win_error.addstr(0,0, msg)
            win_error.refresh()

        def tui(stdscr):
            stdscr.clear()

            details_minheight = 3
            legend_height = len(legend)
            options_maxheight = curses.LINES - legend_height - details_minheight

            options = [{'name': 'prefix', 'value': 'FANCYPREFIX', 'default': 'NORMALPREFIX', 'descr': 'prefix option description'}]
            _ptions = {
                        'core': self.get_core_options(),
                        'backend': self.get_backend_options(),
                        'base': self.get_base_options(),
                        #'compiler_args': self.get_compiler_args(),
                        #'linker_args': self.get_linker_args(),
                        'compiler_options': self.get_compiler_options(),
                        'directories': self.get_directories_options(),
                        'project': self.get_base_options(),
                        'testing': self.get_testing_options(),
                      }
            option_index = 0

            pad_options = curses.newpad(len(options), curses.COLS)
            pad_details = curses.newpad(3, curses.COLS)
            win_legend  = curses.newwin(legend_height, curses.COLS, curses.LINES-legend_height-1, 0)
            win_error   = curses.newwin(1, curses.COLS, curses.LINES-1, 0)

            min_width = 30
            min_height = legend_height + details_minheight + 1

            pad_options.refresh(0,0, 0,0, len(options),curses.COLS-1)
            pad_details.refresh(0,0, 0,0, details_minheight,curses.COLS-1)
            tui_draw_legend(win_legend)

            tui_draw_details(pad_details, options[option_index])

            while True:
                key = stdscr.getkey()

                if key is 'q':
                    self.save()
                    return

                if key in ('KEY_RESIZE'):
                    options_maxheight = curses.LINES - legend_height - details_minheight
                    tui_draw_options(pad_options, option_index, options_maxheight)
                    tui_error(win_error, 'new size: {}x{}'.format(options_maxheight,curses.COLS))

                if options_maxheight < min_height or curses.COLS < min_width:
                    tui_error(win_error, 'Please resize screen to at least {}x{}'.format(min_height, min_width))
                    continue

                if key in ('\n'):
                    tui_error(win_error, 'enter')
                elif key in ('KEY_DOWN', 'KEY_UP', 'j', 'k'):
                    tui_error(win_error, 'arrow key: {}'.format(key))
                    #TODO
                    # option_index +/- 1
                    # while index < pad_options.top:
                    #   pad_options.scroll(1)
                    # while index > pad_options.bottom:
                    #   pad_options.scroll(-1)
                elif key in (' ', 'KEY_NPAGE', 'KEY_PPAGE'):
                    tui_error(win_error, 'page up/down')
                elif key in ('KEY_DC'):
                        tui_set_option(options[option_index]['name'],
                                       options[option_index]['default'],
                                       win_error)
                elif key not in ('KEY_RESIZE', 'q'):
                    tui_error(win_error, 'unbound key: {}'.format(key))

        curses.wrapper(tui)


def run(args):
    args = mesonlib.expand_arguments(args)
    if not args:
        args = [os.getcwd()]
    options = parser.parse_args(args)
    if len(options.directory) > 1:
        print('%s <build directory>' % args[0])
        print('If you omit the build directory, the current directory is substituted.')
        return 1
    if not options.directory:
        builddir = os.getcwd()
    else:
        builddir = options.directory[0]
    try:
        c = Conf(builddir)
        save = False
        if len(options.sets) > 0:
            c.set_options(options.sets)
            save = True
        elif options.clearcache:
            c.clear_cache()
            save = True
        if save:
            c.save()
        if options.dump is not False:
            c.dump_conf(options.dump)
        elif options.tui:
            c.show_tui()
        elif not save:
            c.print_conf()
    except ConfException as e:
        print('Meson configurator encountered an error:\n')
        print(e)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
