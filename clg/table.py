# coding: utf-8 -*-

import io
import os
import sys
import csv
import subprocess

width = lambda: int(subprocess.check_output(['tput', 'cols']))
height = lambda: int(subprocess.check_output(['tput', 'lines']))

class CLGTableError(Exception):
    pass


class Table:
    def __init__(self, page=False, autoflush=False, output_file=None):
        self.output_file = output_file
        if self.output_file:
            # Create directory.
            if not os.path.exists(os.path.dirname(self.output_file)):
                os.makedirs(os.path.dirname(self.output_file))
            # Remove file if exists.
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
        self.page = page
        self.autoflush = autoflush
        self.buffer = []

    def _autoflush(func):
        def wrapper(self, *args, **kwargs):
            func(self, *args, **kwargs)
            if self.autoflush:
                self.flush()
        return wrapper

    @_autoflush
    def add_header(self, *args, **kwargs):
        raise NotImplementedError()

    @_autoflush
    def add_line(self, *args, **kwargs):
        raise NotImplementedError()

    def flush(self):
        if self.output_file:
            with open(self.output_file, 'a') as fhandler:
                fhandler.write('\n'.join(self.buffer))
        elif self.page:
            import os, pydoc
            os.environ['PAGER'] = 'less -c -r'
            pydoc.pager('\n'.join(self.buffer))
        else:
            print('\n'.join(self.buffer))
        self.buffer = []


class Text(Table):
    def __init__(self, page=False, autoflush=False, output_file=None,
                 sizes=None, borders_color=None, text_color=None):
        Table.__init__(self, page, autoflush, output_file)
        self.page = page
        self.sizes = sizes
        self.borders_color = borders_color
        self.text_color = text_color

    def _colorize(self, color, value):
        return '\033[%sm%s\033[00m' % (color, value)

    @Table._autoflush
    def add_border(self, sizes=None, color=None):
        color = color or self.borders_color
        line = '+'
        for idx, size in enumerate(sizes or self.sizes):
            line += '-' * size
            line += '+'
        if color:
            line = self._colorize(color, line)
        self.buffer.append(line)

    @Table._autoflush
    def add_line(self, values, sizes=None, colors=None, border_color=None, newline_indent=1):
        sizes = sizes or self.sizes
        border_color = border_color or self.borders_color
        colors = colors or [self.text_color for __ in range(len(sizes))]

        if sizes is None:
            raise TableError('no sizes')
        if len(sizes) != len(values):
            raise TableError('length of sizes is different from length of values')

        lines = []
        for idx, value in enumerate(values):
            size = sizes[idx] - 2
            if not isinstance(value, str):
                value = str(value)

            line_number = 0
            column_lines = []

            # Split column value on new line.
            value_lines = value.split('\n')
            for line in value_lines:
                # Split line on word.
                line = line.split(' ')
                cur_line = ' '
                while line:
                    word = line.pop(0)
                    new_line = cur_line + word + ' '
                    if len(new_line) > size + 2:
                        if cur_line == ' ':
                            cur_line = new_line
                            column_lines.append(cur_line)
                            cur_line = ' ' * indent + ' '
                        else:
                            cur_line += ' ' * (size + 2 - len(cur_line))
                            column_lines.append(cur_line)
                            cur_line = ' ' * indent + ' ' + word + ' '
                    else:
                        cur_line = new_line
                cur_line += ' ' * (size + 2 - len(cur_line))
                column_lines.append(cur_line)

            # Add column lines.
            for line in column_lines:
                if line_number > len(lines) - 1:
                    # Initialize a new line.
                    new_line = []
                    for __ in range(len(sizes)):
                       new_column = ' ' * sizes[__]
                       if colors[idx]:
                           new_column = self._colorize(colors[idx], new_column)
                       new_line.append(new_column)
                    lines.append(new_line)
                if colors[idx]:
                    line = self._colorize(colors[idx], line)
                lines[line_number][idx] = line
                line_number += 1

        border = '|' if not border_color else self._colorize(border_color, '|')
        self.buffer.extend(border + border.join(line) + border for line in lines)


class CSV(Table):
    def __init__(self, page=False, autoflush=False, output_file=None, separator=','):
        Table.__init__(self, page, autoflush, output_file)
        self.separator = separator

    @Table._autoflush
    def add_line(self, values):
        line = io.StringIO()
        csv_line = csv.writer(line, delimiter=self.separator, quoting=csv.QUOTE_ALL)
        csv_line.writerow(values)
        self.buffer.append(line.getvalue().strip())


class Dokuwiki(Table):
    def __init__(self, page=False, autoflush=False, output_file=None):
        Table.__init__(self, page, autoflush, output_file)

    @Table._autoflush
    def add_line(self, values, separator='|'):
        # Replace newline separator.
        values = [value.replace('\n', '\\\\') for value in values]

        self.buffer.append(
            '%s %s %s' % (separator, (' %s ' % separator).join(values), separator))


def init(args, **kwargs):
    format = args['format'] or kwargs.pop('format', 'text')
    page = args['page'] or kwargs.pop('page', False)
    autoflush = args['autoflush'] or kwargs.pop('autoflush', False)
    output_file = args['output_file'] or kwargs.pop('output_file', None)

    if format == 'text':
        content = Text(page, autoflush, output_file, **kwargs)
    elif format == 'csv':
        separator = args['separator'] or kwargs.pop('separator', ',')
        content = CSV(page, autoflush, output_file, separator)
    elif format == 'dokuwiki':
        content = Dokuwiki(page, autoflush, output_file)
    else:
        raise CLGTableError('invalid format: %s' % format)

    setattr(sys.modules[__name__], 'format', format)
    setattr(sys.modules[__name__], 'content', content)

def add_border(*args, **kwargs):
    if format == 'text':
        content.add_border(*args, **kwargs)
    elif format == 'csv':
        return
    elif format == 'dokuwiki':
        return

def add_header(values, **kwargs):
    if format == 'text':
        content.add_line(values, **kwargs)
    elif format == 'csv':
        content.add_line(values)
    elif format == 'dokuwiki':
        content.add_line(values, separator='^')

def add_line(values, **kwargs):
    if format == 'text':
        content.add_line(values, **kwargs)
    elif format == 'csv':
        content.add_line(values)
    elif format == 'dokuwiki':
        content.add_line(values)

def flush():
    content.flush()

def buffer():
    return content._buffer
