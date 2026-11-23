from sm.ecl import BASE, BUFSIZE, operands, word, vectors, OPS as FAMILY_OPS

OPS = dict(FAMILY_OPS)
OPS.update({0x0C: ('SETUP_MONSTER', 4), 0x1D: ('CONTINUE', 0), 0x1F: ('JOURNAL', 1),
            0x22: ('YES_NO', 0), 0x23: ('REDRAW_EXIT', 0), 0x27: ('TREASURE', 4),
            0x29: ('NO_OPERATION', 0), 0x2C: ('SOUND', 1), 0x31: ('PROMPT_MENU', 2),
            0x3C: ('SHOP', 1)})
VARCOUNT = {0x15: 3, 0x25: 2, 0x26: 2, 0x27: 4, 0x2B: 2, 0x31: 2}
SKIPCOUNT = {op: count for op, (_, count) in OPS.items()}
SKIPCOUNT.update({0x0C: 3, 0x15: 0, 0x25: 0, 0x26: 0, 0x27: 0, 0x2B: 0,
                 0x31: 0, 0x34: 1, 0x36: 1})


def decode(code, pc, resolve=None):
    op = code[pc - BASE]
    if op not in OPS:
        return op, None, pc + 1
    args, following = operands(code, pc, OPS[op][1])
    if op in VARCOUNT:
        count_arg = args[VARCOUNT[op] - 1]
        if count_arg[0] in (0, 2): count = word(count_arg)
        elif resolve is not None: count = resolve(count_arg)
        else: return op, None, following
        extra, following = operands(code, following - 1, count & 255)
        args += extra
    return op, args, following


def skip_end(code, pc):
    return operands(code, pc, SKIPCOUNT.get(code[pc - BASE], 0))[1]


def trace(code):
    vec, seen, todo = vectors(code), {}, list(vectors(code))
    while todo:
        pc = todo.pop()
        while BASE + 20 <= pc < BASE + len(code) and pc not in seen:
            op, args, following = decode(code, pc)
            seen[pc] = op, args, following
            if args is None: break
            if op in (1, 2): todo.append(word(args[0]))
            if op in (0x25, 0x26): todo.extend(word(a) for a in args[2:])
            if 0x16 <= op <= 0x1B: todo.append(skip_end(code, following))
            if op in (0, 1, 0x13, 0x20, 0x23): break
            pc = following
    return vec, seen


def test():
    from .data import Assets
    for code in Assets().scripts().values():
        vec, seen = trace(code)
        assert len(vec) == 5 and seen
        assert all(args is not None for _, args, _ in seen.values())
