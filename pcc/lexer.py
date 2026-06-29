"""Lexical analyzer: converts Python source into a token stream.

Handles indentation (INDENT/DEDENT tokens), string escapes, numeric
literals (int/float), comments, and line continuation inside brackets.
"""

from .tokens import Token, TokenType, KEYWORDS


class LexError(Exception):
    def __init__(self, msg, line, col):
        super().__init__(f"LexError at line {line}, col {col}: {msg}")
        self.line = line
        self.col = col


_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\",
    "'": "'", '"': '"', "0": "\0", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
}


def _decode_string(raw, line, col):
    """Decode a string literal body (without surrounding quotes), handling escapes."""
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\" and i + 1 < n:
            nxt = raw[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if nxt == "x" and i + 3 < n:
                try:
                    out.append(chr(int(raw[i + 2:i + 4], 16)))
                    i += 4
                    continue
                except ValueError:
                    pass
            # Unknown escape: keep backslash + char
            out.append("\\")
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


class Lexer:
    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        # Indentation stack; 0 is always the base.
        self.indents = [0]
        # Track open bracket depth: when > 0, newlines are suppressed.
        self.paren_depth = 0
        # Whether the current line is blank / comment-only (used for indentation rules).
        self.at_line_start = True

    def error(self, msg):
        raise LexError(msg, self.line, self.col)

    def peek(self, off=0):
        p = self.pos + off
        if p < len(self.source):
            return self.source[p]
        return ""

    def advance(self):
        c = self.source[self.pos]
        self.pos += 1
        if c == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return c

    def tokenize(self):
        while self.pos < len(self.source):
            if self.at_line_start and self.paren_depth == 0:
                self._handle_indentation()
                self.at_line_start = False
                # After handling indentation, a blank/comment line means we stay
                # at line start handling for the next iteration.
                if self.pos >= len(self.source):
                    break
                c = self.peek()
                if c == "\n":
                    self.advance()
                    # If the line had meaningful content (e.g. a closing '}'
                    # that brought paren_depth back to 0), emit a NEWLINE so
                    # the parser can terminate the statement.
                    if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
                        self.tokens.append(Token(TokenType.NEWLINE, "\n", self.line - 1, 1))
                    self.at_line_start = True
                    continue
                if c == "#":
                    # skip to end of line
                    while self.pos < len(self.source) and self.peek() != "\n":
                        self.advance()
                    continue

            c = self.peek()
            if c == "\n":
                self.advance()
                if self.paren_depth == 0:
                    # Emit a NEWLINE only if the last meaningful token wasn't a NEWLINE.
                    if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
                        self.tokens.append(Token(TokenType.NEWLINE, "\n", self.line - 1, 1))
                self.at_line_start = True
                continue

            if c == "#":
                while self.pos < len(self.source) and self.peek() != "\n":
                    self.advance()
                continue

            if c in " \t":
                self.advance()
                continue

            if c == "\\" and self.peek(1) == "\n":
                # Explicit line continuation
                self.advance()
                self.advance()
                continue

            if c.isdigit() or (c == "." and self.peek(1).isdigit()):
                self._read_number()
                continue

            if c == '"' or c == "'":
                self._read_string()
                continue

            # f-string prefix: f"..." or f'...'
            if (c in 'fF' and self.peek(1) in ('"', "'")):
                self.advance()  # consume 'f'
                self._read_fstring()
                continue
            if (c in 'rR' and self.peek(1) in 'fF' and self.peek(2) in ('"', "'")):
                self.advance(); self.advance()
                self._read_fstring()
                continue
            if (c in 'fF' and self.peek(1) in 'rR' and self.peek(2) in ('"', "'")):
                self.advance(); self.advance()
                self._read_fstring()
                continue
            # raw string prefix: r"..." or r'...' (no escape processing)
            if (c in 'rR' and self.peek(1) in ('"', "'")):
                self.advance()  # consume 'r'
                self._read_raw_string()
                continue

            if c.isalpha() or c == "_":
                self._read_identifier()
                continue

            self._read_operator()

        # Final newline if needed
        if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
            self.tokens.append(Token(TokenType.NEWLINE, "\n", self.line, 1))
        # Close all open indents
        while len(self.indents) > 1:
            self.indents.pop()
            self.tokens.append(Token(TokenType.DEDENT, None, self.line, 1))
        self.tokens.append(Token(TokenType.EOF, None, self.line, 1))
        return self.tokens

    def _handle_indentation(self):
        # Count leading whitespace (spaces; tabs treated as 8-space stops but we
        # mainly target spaces; a tab counts as moving to next multiple of 8).
        indent = 0
        start_pos = self.pos
        while self.pos < len(self.source):
            c = self.peek()
            if c == " ":
                indent += 1
                self.advance()
            elif c == "\t":
                indent = (indent // 8 + 1) * 8
                self.advance()
            else:
                break
        # If line is blank or comment-only, do not emit INDENT/DEDENT.
        if self.pos >= len(self.source) or self.peek() == "\n" or self.peek() == "#":
            return
        cur = self.indents[-1]
        if indent > cur:
            self.indents.append(indent)
            self.tokens.append(Token(TokenType.INDENT, None, self.line, 1))
        else:
            while indent < self.indents[-1]:
                self.indents.pop()
                self.tokens.append(Token(TokenType.DEDENT, None, self.line, 1))
            if indent != self.indents[-1]:
                self.error("inconsistent indentation")

    def _read_number(self):
        start_line, start_col = self.line, self.col
        s = ""
        is_float = False

        # Hex/octal/binary integer literals: 0x, 0o, 0b (with optional underscores)
        if self.peek() == "0":
            nxt = self.peek(1)
            if nxt in ("x", "X"):
                self.advance(); self.advance()  # consume "0x"
                digits = ""
                while self.pos < len(self.source) and (self.peek().isdigit() or self.peek() in "abcdefABCDEF_"):
                    ch = self.peek()
                    if ch != "_":
                        digits += ch
                    self.advance()
                if not digits:
                    self.error("invalid hexadecimal literal")
                self.tokens.append(Token(TokenType.INTEGER, int(digits, 16), start_line, start_col))
                return
            if nxt in ("o", "O"):
                self.advance(); self.advance()  # consume "0o"
                digits = ""
                while self.pos < len(self.source) and self.peek() in "01234567_":
                    ch = self.peek()
                    if ch != "_":
                        digits += ch
                    self.advance()
                if not digits:
                    self.error("invalid octal literal")
                self.tokens.append(Token(TokenType.INTEGER, int(digits, 8), start_line, start_col))
                return
            if nxt in ("b", "B"):
                self.advance(); self.advance()  # consume "0b"
                digits = ""
                while self.pos < len(self.source) and self.peek() in "01_":
                    ch = self.peek()
                    if ch != "_":
                        digits += ch
                    self.advance()
                if not digits:
                    self.error("invalid binary literal")
                self.tokens.append(Token(TokenType.INTEGER, int(digits, 2), start_line, start_col))
                return

        # Decimal integer or float (with optional underscore separators)
        while self.pos < len(self.source) and (self.peek().isdigit() or self.peek() == "." or self.peek() == "_"):
            ch = self.peek()
            if ch == ".":
                if is_float:
                    break
                # Ensure it's a decimal point, not attribute access on int like 1.bit_length()
                # For our subset, treat as float.
                is_float = True
            s += ch
            self.advance()
        # exponent
        if self.peek() in ("e", "E"):
            is_float = True
            s += self.advance()
            if self.peek() in ("+", "-"):
                s += self.advance()
            while self.pos < len(self.source) and (self.peek().isdigit() or self.peek() == "_"):
                ch = self.peek()
                if ch != "_":
                    s += ch
                self.advance()
        # Strip underscore separators before numeric conversion
        s = s.replace("_", "")
        if is_float:
            self.tokens.append(Token(TokenType.FLOAT, float(s), start_line, start_col))
        else:
            self.tokens.append(Token(TokenType.INTEGER, int(s), start_line, start_col))

    def _read_fstring(self):
        """Read an f-string, producing an FSTRING token with raw content.
        The parser will split it into literal and expression parts."""
        start_line, start_col = self.line, self.col
        quote = self.advance()
        # Triple-quoted f-strings
        if self.peek() == quote and self.peek(1) == quote:
            self.advance(); self.advance()
            s = ""
            while self.pos < len(self.source):
                if self.peek() == quote and self.peek(1) == quote and self.peek(2) == quote:
                    self.advance(); self.advance(); self.advance()
                    break
                s += self.advance()
            self.tokens.append(Token(TokenType.STRING, ("FSTRING", s), start_line, start_col))
            return
        s = ""
        while self.pos < len(self.source) and self.peek() != quote:
            if self.peek() == "\n":
                self.error("unterminated f-string literal")
            if self.peek() == "\\":
                raw = "\\"
                self.advance()
                if self.pos < len(self.source):
                    raw += self.advance()
                s += _decode_string(raw, self.line, self.col)
                continue
            s += self.advance()
        if self.pos >= len(self.source):
            self.error("unterminated f-string literal")
        self.advance()  # closing quote
        self.tokens.append(Token(TokenType.STRING, ("FSTRING", s), start_line, start_col))

    def _read_raw_string(self):
        """Read a raw string literal: no escape processing."""
        start_line, start_col = self.line, self.col
        quote = self.advance()
        # Triple-quoted raw strings
        if self.peek() == quote and self.peek(1) == quote:
            self.advance(); self.advance()
            s = ""
            while self.pos < len(self.source):
                if self.peek() == quote and self.peek(1) == quote and self.peek(2) == quote:
                    self.advance(); self.advance(); self.advance()
                    break
                s += self.advance()
            self.tokens.append(Token(TokenType.STRING, s, start_line, start_col))
            return
        s = ""
        while self.pos < len(self.source) and self.peek() != quote:
            if self.peek() == "\n":
                self.error("unterminated raw string literal")
            s += self.advance()
        if self.pos >= len(self.source):
            self.error("unterminated raw string literal")
        self.advance()  # closing quote
        self.tokens.append(Token(TokenType.STRING, s, start_line, start_col))

    def _read_string(self):
        start_line, start_col = self.line, self.col
        quote = self.advance()
        # Triple-quoted strings
        if self.peek() == quote and self.peek(1) == quote:
            self.advance()
            self.advance()
            s = ""
            while self.pos < len(self.source):
                if self.peek() == quote and self.peek(1) == quote and self.peek(2) == quote:
                    self.advance(); self.advance(); self.advance()
                    break
                if self.peek() == "\\":
                    # Decode escapes within triple strings too
                    raw = []
                    raw.append(self.advance())
                    while self.pos < len(self.source) and self.peek() not in (quote, "\n") and raw[-1] == "\\":
                        raw.append(self.advance())
                    s += _decode_string("".join(raw), self.line, self.col)
                    continue
                s += self.advance()
            self.tokens.append(Token(TokenType.STRING, s, start_line, start_col))
            return
        s = ""
        while self.pos < len(self.source) and self.peek() != quote:
            if self.peek() == "\n":
                self.error("unterminated string literal")
            if self.peek() == "\\":
                # collect escape
                raw = "\\"
                self.advance()
                if self.pos < len(self.source):
                    raw += self.advance()
                s += _decode_string(raw, self.line, self.col)
                continue
            s += self.advance()
        if self.pos >= len(self.source):
            self.error("unterminated string literal")
        self.advance()  # closing quote
        self.tokens.append(Token(TokenType.STRING, s, start_line, start_col))

    def _read_identifier(self):
        start_line, start_col = self.line, self.col
        s = ""
        while self.pos < len(self.source) and (self.peek().isalnum() or self.peek() == "_"):
            s += self.advance()
        if s in KEYWORDS:
            if s == "and":
                self.tokens.append(Token(TokenType.AND, s, start_line, start_col))
            elif s == "or":
                self.tokens.append(Token(TokenType.OR, s, start_line, start_col))
            elif s == "not":
                self.tokens.append(Token(TokenType.NOT, s, start_line, start_col))
            elif s in ("True", "False"):
                self.tokens.append(Token(TokenType.KEYWORD, s, start_line, start_col))
            elif s == "None":
                self.tokens.append(Token(TokenType.KEYWORD, s, start_line, start_col))
            else:
                self.tokens.append(Token(TokenType.KEYWORD, s, start_line, start_col))
        else:
            self.tokens.append(Token(TokenType.IDENTIFIER, s, start_line, start_col))

    def _read_operator(self):
        start_line, start_col = self.line, self.col
        c = self.peek()
        two = self.source[self.pos:self.pos + 2]
        three = self.source[self.pos:self.pos + 3]

        if three == "**=":
            self.advance(); self.advance(); self.advance()
            self.tokens.append(Token(TokenType.DOUBLE_STAR, "**", start_line, start_col))
            self.tokens.append(Token(TokenType.ASSIGN, "=", start_line, start_col + 2))
            return
        if two == "**":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.DOUBLE_STAR, "**", start_line, start_col))
            return
        if two == "//":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.DOUBLE_SLASH, "//", start_line, start_col))
            return
        if two == "==":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.EQ, "==", start_line, start_col))
            return
        if two == "!=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.NEQ, "!=", start_line, start_col))
            return
        if two == "<=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.LE, "<=", start_line, start_col))
            return
        if two == ">=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.GE, ">=", start_line, start_col))
            return
        if two == "+=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.PLUS_ASSIGN, "+=", start_line, start_col))
            return
        if two == "-=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.MINUS_ASSIGN, "-=", start_line, start_col))
            return
        if two == "*=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.STAR_ASSIGN, "*=", start_line, start_col))
            return
        if two == "/=":
            self.advance(); self.advance()
            self.tokens.append(Token(TokenType.SLASH_ASSIGN, "/=", start_line, start_col))
            return

        single = {
            "+": TokenType.PLUS, "-": TokenType.MINUS, "*": TokenType.STAR,
            "/": TokenType.SLASH, "%": TokenType.PERCENT,
            "<": TokenType.LT, ">": TokenType.GT,
            "=": TokenType.ASSIGN,
            "(": TokenType.LPAREN, ")": TokenType.RPAREN,
            "[": TokenType.LBRACKET, "]": TokenType.RBRACKET,
            "{": TokenType.LBRACE, "}": TokenType.RBRACE,
            ":": TokenType.COLON, ",": TokenType.COMMA, ".": TokenType.DOT,
            "@": TokenType.AT, ";": TokenType.SEMI,
        }
        if c in single:
            self.advance()
            if c in ("(", "[", "{"):
                self.paren_depth += 1
            elif c in (")", "]", "}"):
                if self.paren_depth > 0:
                    self.paren_depth -= 1
            self.tokens.append(Token(single[c], c, start_line, start_col))
            return
        self.error(f"unexpected character {c!r}")
