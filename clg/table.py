# coding: utf-8 -*-

import io
import os
import sys
import csv
import subprocess
from pprint import pprint
from namedlist import namedlist

STYLES = {
    'modern': {
        'topleft': '┌',
        'topright':'┐',
        'bottomleft': '└',
        'bottomright': '┘',
        'vertical': '│',
        'horizontal': '─',
        'intersection': '┼',
        'topinter': '┬',
        'bottominter': '┴',
        'leftinter': '├',
        'rightinter': '┤',
        'none': ' '
    },
    'classic': {
        'topleft': '+',
        'topright': '+',
        'bottomleft': '+',
        'bottomright': '+',
        'vertical': '|',
        'horizontal': '-',
        'intersection': '+',
        'topinter': '+',
        'bottominter': '+',
        'leftinter': '+',
        'rightinter': '+',
        'none': ' '
    }
}
_SELF = sys.modules[__name__]

# Define a cli logger.
import logging
logger = logging.getLogger('clg-table')
logger.setLevel('WARN')
cli_handler = logging.StreamHandler()
cli_handler.setFormatter(logging.Formatter('(clg-table) %(levelname)s: %(message)s'))
logger.addHandler(cli_handler)

ColumnWidths = namedlist('ColumWidths', ('width', 'min_width', 'max_width', 'text_width'))
BorderVisibility = namedlist('BorderVisibility', ('top', 'right', 'bottom', 'left'))

term_width = lambda: int(subprocess.check_output(['tput', 'cols']))
term_height = lambda: int(subprocess.check_output(['tput', 'lines']))

class CLGTableError(Exception):
    pass

class Buffer(list):
    def get(self, index, default):
        try:
            return self[index]
        except IndexError:
            return default

    def set(self, index, value, fill='?'):
        try:
            self[index] = value or self[index] or fill
        except IndexError:
            for _ in range(len(self), index):
                self.append(fill)
            self.append(value or fill)
        return self[index]

    def setdefault(self, index, value, fill='?'):
        try:
            return self[index]
        except IndexError:
            for _ in range(len(self), index):
                self.append(fill)
            self.append(value)
            return self[index]

def init(args, **kwargs):
    output_format = args.format or 'text'
    output_class = getattr(_SELF, '{:s}Table'.format(output_format.capitalize()))

    params = {'page': args.page or False,
              'output_file': args.output_file or None}
    if args.format == 'text':
        params.update(widths=kwargs.pop('widths', []),
                      title=kwargs.pop('title', None),
                      style=kwargs.pop('style', 'modern'),
                      text_color=kwargs.pop('text_color', None),
                      border_color=kwargs.pop('border_color', None))
    if args.format == 'csv':
        params.update(separator=args.csv_separator or ';')

    return output_class(**params)


class Row:
    def __init__(self, *cells):
        self.cells = cells

class Header(Row):
    def __init__(self, *cells):
        Row.__init__(self, *cells)

class Cell:
    def __init__(self, text, **kwargs):
        self.text = (str(text).split('\n')
                     if not isinstance(text, (list, tuple))
                     else list(text))
        self.min_width = kwargs.get('min_width', -1)
        self.width = kwargs.get('width', -1)
        self.max_width = kwargs.get('max_width', -1)
        self.padding_top = kwargs.get('padding_top', 0)
        self.padding_bottom = kwargs.get('padding_bottom', 0)
        self.padding_left = kwargs.get('padding_left', 1)
        self.padding_right = kwargs.get('padding_right', 1)
        self.halign = kwargs.get('halign', 'left')
        self.valign = kwargs.get('valign', 'top')
        self.newline_indent = kwargs.get('newline_indent', 1)
        self.border_color = kwargs.get('border_color', None)
        self.text_color = kwargs.get('text_color', None)
        self.border_visibility = BorderVisibility(
            *kwargs.get('border_visibility',
                        (not kwargs.get('hide_border_top', False),
                         not kwargs.get('hide_border_right', False),
                         not kwargs.get('hide_border_bottom', False),
                         not kwargs.get('hide_border_left', False))))

    def get_min_width(self):
        return (self.min_width
                if self.min_width != -1
                else (self.padding_left + 1 + self.padding_right))

    def get_text_width(self):
        return (self.padding_left
                + (max(len(val) for val in self.text) if self.text else 0)
                + self.padding_right)

    def add_padding(self, value):
        return ' ' * self.padding_left + value + ' ' * self.padding_right

    def set_alignment(self, value, width):
        alignment = {'left': '<', 'center': '^', 'right': '>'}[self.halign]
        width = width + self.padding_left + self.padding_right
        return '{:{align}{width}s}'.format(value, align=alignment, width=width)

    def format(self, value, width):
        """Add left/right paddings to the value and format with width and alignment."""
        value = ' ' * self.padding_left + value + ' ' * self.padding_right
        alignment = {'left': '<', 'center': '^', 'right': '>'}[self.halign]
        width = width + self.padding_left + self.padding_right
        return '{:{align}{width}s}'.format(value, align=alignment, width=width)

    def split_word(self, word, width):
        lines = []
        first_line = True
        while word:
            cur_width = (
                width - self.newline_indent
                if not first_line
                else width)
            string = (
                (' ' * self.newline_indent if not first_line else '')
                + word[0:cur_width])
            lines.append(string)
            word = word[cur_width:]
            first_line = False
        return lines

    def split_text(self, width):
        at_start = (lambda line:
            line == '' or line == ' ' * self.newline_indent or line.startswith(' '))

        # For padding top and bottom, add empty lines at start/end of the text.
        for _ in range(self.padding_top):
            self.text.insert(0, ' ')
        for _ in range(self.padding_bottom):
            self.text.append(' ')

        # For calculated text length, ignore left/right paddings which are added
        # for each lines.
        width = width - self.padding_left - self.padding_right
        lines = []
        for line in self.text:
            # No split needed if the length of the current line is inferior to the width.
            if len(line) <= width:
                lines.append(self.format(line, width))
                continue

            # Split current line on words.
            words = line.split(' ')
            cur_line = ''
            while words:
                word = words.pop(0)

                # Add word to the current line.
                if not word:
                    new_line = cur_line + ' '
                else:
                    new_line = cur_line + ('' if at_start(cur_line) else ' ') + word

                if len(new_line) > width:
                    # Manage the case where the word is bigger than width.
                    if len(word) > width:
                        lines.extend(self.format(string, width)
                                     for string in self.split_word(new_line, width))
                        cur_line = ' ' * self.newline_indent
                    # Add the current line, and initialize a new line with the word.
                    else:
                        lines.append(self.format(cur_line, width))
                        cur_line = ' ' * self.newline_indent + word
                        # If the word with the newline indentation is bigger than width,
                        # split the word.
                        if len(cur_line) > width:
                            lines.extend(self.format(string, width)
                                         for string in self.split_word(cur_line, width))
                            cur_line = ' ' * self.newline_indent
                else:
                    cur_line = new_line

            # Add the remaining line if not empty.
            if not at_start(cur_line):
                lines.append(self.format(cur_line, width))

        self.text = lines


class Table(list):
    def __init__(self, page=False, output_file=None):
        self.page = page
        self.output_file = output_file

    def flush(self):
        lines = '\n'.join(''.join(line) for line in self.render())
        self.rows = []

        if self.output_file:
            with open(self.output_file, 'w') as fhandler:
                fhandler.write(lines)
        elif self.page:
            import os, pydoc
            os.environ['PAGER'] = 'less -r -c'
            pydoc.pager(lines)
        else:
            print(lines)


class TextTable(Table):
    def __init__(self, widths, page=False, output_file=None, title=None, style='modern',
                 text_color=None, border_color=None):
        Table.__init__(self, page, output_file)
        self.title = title
        self.style = style
        self.widths = []
        self.heigths = []

    def get_border(self, side, row_idx, col_idx):
        first_row = row_idx == 0
        last_row = row_idx == len(self) - 1
        first_col = col_idx == 0
        last_col = col_idx == len(self.widths) - 1

        cell = self[row_idx].cells[col_idx]
        symbol = None
        color = cell.border_color
        if side == 'topleft':
            if first_row and first_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'top':
                        {'left': STYLES[self.style]['topleft'],
                         '!left': STYLES[self.style]['horizontal']},
                     '!top':
                        {'left': STYLES[self.style]['vertical'],
                         '!left': STYLES[self.style]['none']}})
        elif side == 'tophoriz':
            if first_row:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'top': STYLES[self.style]['horizontal'],
                     '!top': STYLES[self.style]['none']})
#                symbol = symbol * self.widths[col_idx]
        elif side == 'topright':
            if first_row and last_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'top':
                        {'right': STYLES[self.style]['topright'],
                         '!right': STYLES[self.style]['horizontal']},
                     '!top':
                        {'right': STYLES[self.style]['vertical'],
                         '!right': STYLES[self.style]['none']}})
            elif first_row:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'top':
                        {'+top':
                            {'&right': STYLES[self.style]['topinter'],
                             '!&right': STYLES[self.style]['horizontal']},
                         '!+top':
                            {'&right': STYLES[self.style]['topright'],
                             '!&right': STYLES[self.style]['horizontal']}},
                     '!top':
                        {'+top':
                            {'&right': STYLES[self.style]['topleft'],
                             '!&right': STYLES[self.style]['horizontal']},
                         '!+top':
                            {'&right': STYLES[self.style]['vertical'],
                             '!&right': STYLES[self.style]['none']}}})
                color = self.get_color(row_idx, col_idx, 1, 0) or cell.border_color

        elif side == 'leftvert':
            if first_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'left': STYLES[self.style]['vertical'],
                     '!left': STYLES[self.style]['none']})
        elif side == 'rightvert':
            symbol = self.get_symbol(
                row_idx, col_idx,
                {'&right': STYLES[self.style]['vertical'],
                 '!&right': STYLES[self.style]['none']})
            color = self.get_color(row_idx, col_idx, 1, 0) or cell.border_color

        elif side == 'bottomleft':
            if last_row and first_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'left':
                        {'bottom': STYLES[self.style]['bottomleft'],
                         '!bottom': STYLES[self.style]['vertical']},
                     '!left':
                        {'bottom': STYLES[self.style]['horizontal'],
                         '!bottom': STYLES[self.style]['none']}})
            elif first_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'left':
                        {'+left':
                            {'&bottom': STYLES[self.style]['leftinter'],
                             '!&bottom': STYLES[self.style]['vertical']},
                         '!+left':
                            {'&bottom': STYLES[self.style]['bottomleft'],
                             '!&bottom': STYLES[self.style]['none']}},
                     '!left':
                        {'+left':
                            {'&bottom': STYLES[self.style]['topleft'],
                             '!&bottom': STYLES[self.style]['none']},
                         '!+left':
                            {'&bottom': STYLES[self.style]['horizontal'],
                             '!&bottom': STYLES[self.style]['none']}}})
                color = self.get_color(row_idx, col_idx, 0, 1) or cell.border_color
        elif side == 'bottomhoriz':
            symbol = self.get_symbol(
                row_idx, col_idx,
                {'&bottom': STYLES[self.style]['horizontal'],
                 '!&bottom': STYLES[self.style]['none']})
#            symbol = symbol * self.widths[col_idx]
            color = self.get_color(row_idx, col_idx, 0, 1) or cell.border_color
        elif side == 'bottomright':
            if last_row and last_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'right':
                        {'bottom': STYLES[self.style]['bottomright'],
                         '!bottom': STYLES[self.style]['vertical']},
                     '!right':
                        {'bottom': STYLES[self.style]['horizontal'],
                         '!bottom': STYLES[self.style]['none']}})
            elif last_col:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'right':
                        {'+right':
                            {'&bottom': STYLES[self.style]['rightinter'],
                             '!&bottom': STYLES[self.style]['vertical']},
                         '!+right':
                            {'&bottom': STYLES[self.style]['bottomright'],
                             '!&bottom': STYLES[self.style]['none']}},
                     '!right':
                        {'+right':
                            {'&bottom': STYLES[self.style]['topright'],
                             '!&bottom': STYLES[self.style]['none']},
                         '!+right':
                            {'&bottom': STYLES[self.style]['horizontal'],
                             '!&bottom': STYLES[self.style]['none']}}})
                color = self.get_color(row_idx, col_idx, 0, 1) or cell.border_color
            elif last_row:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'bottom':
                        {'&right':
                            {'+bottom': STYLES[self.style]['bottominter'],
                             '!+bottom': STYLES[self.style]['bottomright']},
                         '!&right':
                            {'+bottom': STYLES[self.style]['horizontal'],
                             '!+bottom': STYLES[self.style]['none']}},
                     '!bottom':
                        {'&right':
                            {'+bottom': STYLES[self.style]['bottomleft'],
                             '!+bottom': STYLES[self.style]['vertical']},
                         '!&right':
                            {'+bottom': STYLES[self.style]['none'],
                             '!+bottom': STYLES[self.style]['none']}}})
                color = self.get_color(row_idx, col_idx, 1, 0) or cell.border_color
            else:
                symbol = self.get_symbol(
                    row_idx, col_idx,
                    {'&right':
                        {'&bottom':
                            {'+&right':
                                {'+&bottom': STYLES[self.style]['intersection'],
                                 '!+&bottom': STYLES[self.style]['rightinter']},
                             '!+&right':
                                {'+&bottom': STYLES[self.style]['bottominter'],
                                 '!+&bottom': STYLES[self.style]['bottomright']}},
                         '!&bottom':
                            {'+&right':
                                {'+&bottom': STYLES[self.style]['leftinter'],
                                 '!+&bottom': STYLES[self.style]['vertical']},
                             '!+&right':
                                {'+&bottom': STYLES[self.style]['bottomleft'],
                                 '!+&bottom': STYLES[self.style]['none']}}},
                     '!&right':
                        {'&bottom':
                            {'+&right':
                                {'+&bottom': STYLES[self.style]['topinter'],
                                 '!+&bottom': STYLES[self.style]['topright']},
                             '!+&right':
                                {'+&bottom': STYLES[self.style]['horizontal'],
                                 '!+&bottom': STYLES[self.style]['none']}},
                         '!&bottom':
                            {'+&right':
                                {'+&bottom': STYLES[self.style]['topleft'],
                                 '!+&bottom': STYLES[self.style]['none']},
                             '!+&right':
                                {'+&bottom': STYLES[self.style]['horizontal'],
                                 '!+&bottom': STYLES[self.style]['none']}}}})
                color = (self.get_color(row_idx, col_idx, 1, 1)
                      or self.get_color(row_idx, col_idx, 0, 1)
                      or self.get_color(row_idx, col_idx, 1, 0)
                      or cell.border_color)

        return self.set_color(symbol, color) if symbol else None

    def get_color(self, row_idx, col_idx, x, y):
        cell = self[row_idx].cells[col_idx]
        try:
            next_cell = self[row_idx + y]
            try:
                return next_cell.cells[col_idx + x].border_color
            except IndexError:
                return cell.border_color
        except IndexError:
            return cell.border_color

    def get_symbol(self, row_idx, col_idx, mapping):
        if not isinstance(mapping, dict):
            return mapping

        key = list(reversed(sorted(mapping)))[0]
        if key.startswith('+'):
            key = key[1:]
            if key.startswith('&'):
                visibility = (
                    self.get_visibility(row_idx + 1, col_idx, 1, 0, key[1:])
                    if key in ('left', 'right')
                    else self.get_visibility(row_idx, col_idx + 1, 0, 1, key[1:]))
            else:
                visibility = (
                    getattr(self[row_idx + 1].cells[col_idx].border_visibility, key)
                    if key in ('left', 'right')
                    else getattr(self[row_idx].cells[col_idx + 1].border_visibility, key))
            key = '+' + key
        else:
            if key.startswith('&'):
                visibility = (
                    self.get_visibility(row_idx, col_idx, 1, 0, key[1:])
                    if key in ('left', 'right')
                    else self.get_visibility(row_idx, col_idx, 0, 1, key[1:]))
            else:
                visibility = getattr(self[row_idx].cells[col_idx].border_visibility, key)

        key = '!' + key if not visibility else key
        return self.get_symbol(row_idx, col_idx, mapping[key])

    def get_visibility(self, row_idx, col_idx, x, y, side):
        cell = self[row_idx].cells[col_idx]
        rside = {'top': 'bottom', 'right': 'left', 'bottom': 'top', 'left': 'right'}[side]
        try:
            next_cell = self[row_idx + y]
            try:
                visibility = getattr(next_cell.cells[col_idx + x].border_visibility, rside)
                return getattr(cell.border_visibility, side) and visibility
            except IndexError:
                return getattr(cell.border_visibility, side)
        except IndexError:
            return getattr(cell.border_visibility, side)

    def set_color(self, text, color):
        return '\x1b[{:s}m{:s}\x1b[00m'.format(color, text) if color else text

    def render(self):
        lines = Buffer()

        def get_row_height(row):
            heights = []
            for col_idx, cell in enumerate(row.cells):
                cell.split_text(self.widths[col_idx])
                heights.append(len(cell.text))
            return max(heights)

        def add(row_idx, value, n=1):
            lines.setdefault(row_idx, [])
            if value:
                lines[row_idx].extend([value] * n)

        if not self.widths:
            self._get_columns_widths()

        text_row_idx = 0
        for row_idx, row in enumerate(self):
            height = get_row_height(row)

            for col_idx, cell in enumerate(row.cells):
                # Add top border.
                add(text_row_idx, self.get_border('topleft', row_idx, col_idx))
                add(text_row_idx,
                    self.get_border('tophoriz', row_idx, col_idx),
                    self.widths[col_idx])
                add(text_row_idx, self.get_border('topright', row_idx, col_idx))

                # Add text.
                for _ in range(1, height + 1):
                    idx = text_row_idx + _
                    add(idx, self.get_border('leftvert', row_idx, col_idx))
                    try:
                        text = cell.text[_ - 1]
                        add(idx, self.set_color(text, cell.text_color))
                    except IndexError:
                        add(idx,
                            self.set_color(' ', cell.text_color),
                            self.widths[col_idx])
                    add(idx, self.get_border('rightvert', row_idx, col_idx))

                # Add bottom border.
                idx = text_row_idx + height + 1
                add(idx, self.get_border('bottomleft', row_idx, col_idx))
                add(idx,
                    self.get_border('bottomhoriz', row_idx, col_idx),
                    self.widths[col_idx])
                add(idx, self.get_border('bottomright', row_idx, col_idx))

            text_row_idx += height + 1
            text_col_idx = 0

        if self.title:
            for idx, char in enumerate(self.title):
                lines[0][idx + 1] = char

        return lines

    def _get_columns_widths(self):
        columns_widths = []
        # For each column, get minimal, defined, maximal and text width.
        for row in self:
            for col_idx, cell in enumerate(row.cells):
                if col_idx >= len(columns_widths):
                    columns_widths.append(ColumnWidths(-1, -1, -1, -1))
                column_widths = columns_widths[col_idx]
                column_widths.width = max((cell.width, column_widths.width))
                column_widths.min_width = max((cell.get_min_width(), column_widths.min_width))
                column_widths.max_width = max((cell.max_width, column_widths.max_width))
                column_widths.text_width = max((cell.get_text_width(), column_widths.text_width))

        # Distribute widths based on terminal width and number of borders.
        remaining_size = term_width() - len(columns_widths) - 1
        status = []
        for column in columns_widths:
            if column.width != -1:
                self.widths.append(column.width)
                status.append(True)
                remaining_size -= column.width
            else:
                self.widths.append(column.min_width)
                status.append(True if column.text_width <= column.min_width else False)
                remaining_size -= column.min_width

        while True:
            if remaining_size <= 0 or all(status):
                break

            for idx, column in enumerate(columns_widths):
                if status[idx]:
                    continue

                preferred_width = (
                    column.max_width if column.max_width != -1 else column.text_width)

                # Increment current column.
                if self.widths[idx] < preferred_width:
                    self.widths[idx] += 1
                    remaining_size -= 1

                    # Mark column as done if column's width is equal to preferred width.
                    if self.widths[idx] == preferred_width:
                        status[idx] = True

                    # Stop here if there is nothinh remaining.
                    if remaining_size <= 0:
                        break

        # Check there is no overflow or throw a warning.
        if remaining_size < 0:
            logger.warn(
                'unable to adapt size (terminal size: {:d}, overflow: {:d})!'
                .format(term_width(), -remaining_size))


class CsvTable(Table):
    def __init__(self, page=False, output_file=None, separator=';'):
        Table.__init__(self, page, output_file)


class DokuwikiTable(Table):
    def __init__(self, page=False, output_file=None):
        Table.__init__(self, page, output_file)
