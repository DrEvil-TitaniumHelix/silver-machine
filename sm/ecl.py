"""ECL decoder. Tables ported verbatim from GBU decode/tools/ecldis.py (Curse rules + SECRET op 41; ECL_DELTA 1-2, 5).
Record -> code: bytes after the 2-B header `88 13` sit at cell 8000h + i (LoadEclBlock; InitVM PC := 8000h, ov09:01F5).
Operand = (type, lo, hi, text): type 0 byte imm, 1 mem byte, 2 word imm, 3 mem word, 80h packed text, 81h string from cell."""
from sm.text import packed_text as text

BASE, BUFSIZE = 0x8000, 0x1E00
OPS = {
    0x00: ("EXIT", 0), 0x01: ("GOTO", 1), 0x02: ("GOSUB", 1), 0x03: ("COMPARE", 2),
    0x04: ("ADD", 3), 0x05: ("SUBTRACT", 3), 0x06: ("DIVIDE", 3), 0x07: ("MULTIPLY", 3),
    0x08: ("RANDOM", 2), 0x09: ("SAVE", 2), 0x0A: ("LOAD_CHARACTER", 1), 0x0B: ("LOAD_MONSTER", 3),
    0x0C: ("SETUP_MONSTER", 3), 0x0D: ("APPROACH", 0), 0x0E: ("PICTURE", 1), 0x0F: ("INPUT_NUMBER", 2),
    0x10: ("INPUT_STRING", 2), 0x11: ("PRINT", 1), 0x12: ("PRINTCLEAR", 1), 0x13: ("RETURN", 0),
    0x14: ("COMPARE_AND", 4), 0x15: ("VERTICAL_MENU", 3), 0x16: ("IF_EQ", 0), 0x17: ("IF_NE", 0),
    0x18: ("IF_LT", 0), 0x19: ("IF_GT", 0), 0x1A: ("IF_LE", 0), 0x1B: ("IF_GE", 0),
    0x1C: ("CLEAR_MONSTERS", 0), 0x1D: ("PARTY_STRENGTH", 1), 0x1E: ("CHECK_PARTY", 6),
    0x20: ("NEW_ECL", 1), 0x21: ("LOAD_FILES", 3), 0x22: ("PARTY_SURPRISE", 2), 0x23: ("SURPRISE", 4),
    0x24: ("COMBAT", 0), 0x25: ("ON_GOTO", 2), 0x26: ("ON_GOSUB", 2), 0x27: ("TREASURE", 8),
    0x28: ("ROB", 3), 0x29: ("ENCOUNTER_MENU", 14), 0x2A: ("GET_TABLE", 3), 0x2B: ("HORIZONTAL_MENU", 2),
    0x2C: ("PARLAY", 6), 0x2D: ("CALL", 1), 0x2E: ("DAMAGE", 5), 0x2F: ("AND", 3), 0x30: ("OR", 3),
    0x31: ("SPRITE_OFF", 0), 0x32: ("FIND_ITEM", 1), 0x33: ("PRINT_RETURN", 0), 0x34: ("ECL_CLOCK", 2),
    0x35: ("SAVE_TABLE", 3), 0x36: ("ADD_NPC", 2), 0x37: ("LOAD_PIECES", 3), 0x38: ("PROGRAM", 1),
    0x39: ("WHO", 1), 0x3A: ("DELAY", 0), 0x3B: ("SPELL", 3), 0x3C: ("PROTECTION", 1), 0x3D: ("CLEAR_BOX", 0),
    0x3E: ("DUMP", 0), 0x3F: ("FIND_SPECIAL", 1), 0x40: ("DESTROY_ITEMS", 1), 0x41: ("ADD_EP", 2),
}
VARCOUNT = {0x15: 3, 0x25: 2, 0x26: 2, 0x2B: 2}      # op -> 1-based operand holding the extra count
SKIPCOUNT = {0x15: 0, 0x1F: 2, 0x25: 0, 0x26: 0, 0x2B: 0, 0x34: 1, 0x36: 1}   # SkipInstruction ov09:1F3D table
ENDS = {0x00, 0x01, 0x13, 0x20}
TABLE_OPERAND = {0x2A: 1, 0x35: 2}



def operands(code, pc, n):
    """ReadOperands (ov09:0000): pc = byte before the first operand; returns (ops, pc after). code indexed by cell - BASE."""
    ops = []
    for _ in range(n):
        t, lo = code[pc + 1 - BASE], code[pc + 2 - BASE]; pc += 2
        if t in (1, 2, 3, 0x81): pc += 1; ops.append((t, lo, code[pc - BASE], None))
        elif t == 0x80: ops.append((t, lo, 0, text(code[pc + 1 - BASE: pc + 1 + lo - BASE]))); pc += lo
        else: ops.append((t, lo, 0, None))
    return ops, pc + 1

def word(o): return o[2] * 256 + o[1]

def decode(code, pc):
    """-> (op, ops, next_pc); op without a handler -> (op, None, pc+1)."""
    op = code[pc - BASE]
    if op not in OPS: return op, None, pc + 1
    ops, npc = operands(code, pc, OPS[op][1])
    if op in VARCOUNT:
        o = ops[VARCOUNT[op] - 1]
        if o[0] in (0, 2): more, npc = operands(code, npc - 1, o[1]); ops += more
    return op, ops, npc

def skip_end(code, pc):
    """SkipInstruction: the address after the instruction at pc when an IF is false."""
    op = code[pc - BASE]
    return operands(code, pc, SKIPCOUNT.get(op, OPS[op][1] if op in OPS else 0))[1]

def vectors(code):
    """InitVM: 5 x ReadOperands(1) from PC 8000h (each header entry = op byte + 1 operand) -> vecA..vecE."""
    out, pc = [], BASE
    for _ in range(5): ops, pc = operands(code, pc, 1); out.append(word(ops[0]))
    return out

def trace(code):
    """Static traversal from the 5 vectors (ecldis.trace): {pc: (op, ops, npc)}; data tables (GET/SAVE_TABLE bases) excluded."""
    end, data = BASE + len(code), set()
    while True:
        vec = vectors(code); insns, todo = {}, list(vec)
        while todo:
            pc = todo.pop()
            while BASE + 20 <= pc < end and pc not in insns and pc not in data:
                try: op, ops, npc = decode(code, pc)
                except IndexError: break
                insns[pc] = (op, ops, npc)
                if ops is None: break
                if op in (1, 2) and ops[0][0] in (1, 2, 3): todo.append(word(ops[0]))
                if op in (0x25, 0x26): todo += [word(o) for o in ops[2:]]
                if 0x16 <= op <= 0x1B:
                    try:
                        if code[npc - BASE] in OPS or code[npc - BASE] == 0x1F: todo.append(skip_end(code, npc))
                    except IndexError: pass
                if op in ENDS: break
                pc = npc
        nd = {word(ops[TABLE_OPERAND[op] - 1]) for op, ops, _ in insns.values()
              if op in TABLE_OPERAND and ops and ops[TABLE_OPERAND[op] - 1][0] in (1, 2, 3) and word(ops[TABLE_OPERAND[op] - 1]) >= BASE}
        if nd <= data: return vec, insns
        data |= nd
