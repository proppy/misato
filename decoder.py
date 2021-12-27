from amaranth import *
from amaranth.build import Platform
from amaranth.cli import main_parser, main_runner
from amaranth.back import verilog
from amaranth.sim import Simulator, Settle

from amaranth.asserts import Assert, Assume, Cover

from isa import *

from typing import List


class Decoder(Elaboratable):
    def __init__(self, xlen: XLEN, formal: bool):
        # Inputs
        self.instr  = Signal(xlen.value)

        # Outputs
        self.format  = Signal(Format)
        self.opcode  = Signal(Opcode)
        self.r_type  = Signal()
        self.i_type  = Signal()
        self.u_type  = Signal()
        self.s_type  = Signal()
        self.b_type  = Signal()
        self.j_type  = Signal()
        self.imm     = Signal(xlen.value)
        self.rs1     = Signal(5)
        self.rs2     = Signal(5)
        self.rd      = Signal(5)
        self.funct3  = Signal(Funct3)
        self.funct7  = Signal(Funct7)
        self.u_instr = Signal(U_Type)
        self.trap    = Signal()

        # Config
        self.xlen    = xlen.value
        self.formal  = formal

    def ports(self) -> List[Signal]:
        return [
            self.instr,
            self.format,
            self.opcode,
            self.r_type,
            self.i_type,
            self.s_type,
            self.u_type,
            self.b_type,
            self.j_type,
            self.imm,
            self.rs1,
            self.rs2,
            self.rd,
            self.funct3,
            self.funct7,
            self.u_instr,
            self.trap,
        ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # Internal signals
        opcode = Signal(Opcode)
        rd     = Signal(5)
        rs1    = Signal(5)
        rs2    = Signal(5)
        funct3 = Signal(Funct3)
        funct7 = Signal(Funct7)
        i_imm  = Signal(self.xlen)
        s_imm  = Signal(self.xlen)
        b_imm  = Signal(self.xlen)
        u_imm  = Signal(self.xlen)
        j_imm  = Signal(self.xlen)

        # Extract bit-fields from the instruction
        m.d.comb += [
            opcode.eq(self.instr[:7]),
            rd.eq(self.instr[7:12]),
            rs1.eq(self.instr[15:20]),
            rs2.eq(self.instr[20:25]),
            funct3.eq(Mux(self.u_type, Funct3.ADD, self.instr[12:15])),
            funct7.eq(self.instr[25:]),
            i_imm.eq(Cat(self.instr[20:], Repl(self.instr[31], 20))),
            s_imm.eq(
                Cat(self.instr[7:12], self.instr[25:], Repl(self.instr[31], 20))),
            b_imm.eq(Cat(C(0), self.instr[8:12], self.instr[25:31],
                         self.instr[7], self.instr[31], Repl(self.instr[31], 19))),
            u_imm.eq(Cat(Repl(C(0), 12), self.instr[12:])),
            j_imm.eq(Cat(C(0), self.instr[21:31], self.instr[20],
                         self.instr[12:20], self.instr[31], Repl(self.instr[31], 12))),
            self.rs1.eq(rs1),
            self.rs2.eq(rs2),
            self.rd.eq(rd),
            self.funct3.eq(funct3),
            self.funct7.eq(funct7),
            self.opcode.eq(opcode),
        ]

        # Default values
        m.d.comb += [
            self.r_type.eq(0),
            self.i_type.eq(0),
            self.s_type.eq(0),
            self.b_type.eq(0),
            self.u_type.eq(0),
            self.j_type.eq(0),
            self.imm.eq(0),
        ]

        with m.Switch(opcode):
            with m.Case(Opcode.OP):
                m.d.comb += self.r_type.eq(1)
                m.d.comb += self.format.eq(Format.R_type)
                m.d.comb += self.imm.eq(0)
            with m.Case(Opcode.OP_IMM, Opcode.LOAD):
                m.d.comb += self.i_type.eq(1)
                m.d.comb += self.format.eq(Format.I_type)
                m.d.comb += self.imm.eq(i_imm)
            with m.Case(Opcode.STORE):
                m.d.comb += self.s_type.eq(1)
                m.d.comb += self.format.eq(Format.S_type)
                m.d.comb += self.imm.eq(s_imm)
            with m.Case(Opcode.LUI):
                m.d.comb += self.u_type.eq(1)
                m.d.comb += self.format.eq(Format.U_type)
                m.d.comb += self.imm.eq(u_imm)
                m.d.comb += self.u_instr.eq(U_Type.LUI)
            with m.Case(Opcode.AUIPC):
                m.d.comb += self.u_type.eq(1)
                m.d.comb += self.format.eq(Format.U_type)
                m.d.comb += self.imm.eq(u_imm)
                m.d.comb += self.u_instr.eq(U_Type.AUIPC)
            with m.Case(Opcode.BRANCH):
                m.d.comb += self.b_type.eq(1)
                m.d.comb += self.format.eq(Format.B_type)
                m.d.comb += self.imm.eq(b_imm)
            with m.Case(Opcode.JAL):
                m.d.comb += self.j_type.eq(1)
                m.d.comb += self.format.eq(Format.J_type)
                m.d.comb += self.imm.eq(j_imm)
            with m.Case(Opcode.JALR):
                m.d.comb += self.j_type.eq(1)
                m.d.comb += self.format.eq(Format.I_type)
                m.d.comb += self.imm.eq(i_imm)
            with m.Default():
                m.d.comb += [
                    self.format.eq(Format.Unknown_type),
                    self.r_type.eq(0),
                    self.i_type.eq(0),
                    self.s_type.eq(0),
                    self.u_type.eq(0),
                    self.b_type.eq(0),
                    self.j_type.eq(0),
                    self.imm.eq(0),
                    self.trap.eq(1)
                ]
        
        #
        # Formal verification
        #

        if self.formal:
            # Check if R-type instructions are correctly decoded
            with m.If(self.opcode == Opcode.OP):
                m.d.comb += [
                    Assert(self.r_type == 0b1),
                    Assert(self.i_type == 0b0),
                    Assert(self.s_type == 0b0),
                    Assert(self.b_type == 0b0),
                    Assert(self.u_type == 0b0),
                    Assert(self.j_type == 0b0),
                    Assert(~self.trap),
                    Assert(self.format == Format.R_type)
                ]
            with m.Else():
                m.d.comb += Assert(self.r_type == 0b0)
            
            # Check if I-type instructions are correctly decoded
            with m.If((self.opcode == Opcode.OP_IMM) | (self.opcode == Opcode.LOAD)):
                m.d.comb += [
                    Assert(self.r_type == 0b0),
                    Assert(self.i_type == 0b1),
                    Assert(self.s_type == 0b0),
                    Assert(self.b_type == 0b0),
                    Assert(self.u_type == 0b0),
                    Assert(self.j_type == 0b0),
                    Assert(self.imm == i_imm),
                    Assert(~self.trap),
                    Assert(self.format == Format.I_type)
                ]
            with m.Else():
                m.d.comb += Assert(self.i_type == 0b0)

            # Check if S-type instructions are correctly decoded
            with m.If(self.opcode == Opcode.STORE):
                m.d.comb += [
                    Assert(self.r_type == 0b0),
                    Assert(self.i_type == 0b0),
                    Assert(self.s_type == 0b1),
                    Assert(self.b_type == 0b0),
                    Assert(self.u_type == 0b0),
                    Assert(self.j_type == 0b0),
                    Assert(self.imm == s_imm),
                    Assert(~self.trap),
                    Assert(self.format == Format.S_type)
                ]
            with m.Else():
                m.d.comb += Assert(self.s_type == 0b0)

            # Check if B-type instructions are correctly decoded
            with m.If(self.opcode == Opcode.BRANCH):
                m.d.comb += [
                    Assert(self.r_type == 0b0),
                    Assert(self.i_type == 0b0),
                    Assert(self.s_type == 0b0),
                    Assert(self.b_type == 0b1),
                    Assert(self.u_type == 0b0),
                    Assert(self.j_type == 0b0),
                    Assert(~self.trap),
                    Assert(self.imm == b_imm),
                    Assert(self.format == Format.B_type)
                ]
            with m.Else():
                m.d.comb += Assert(self.b_type == 0b0)

            # Check if U-type instructions are correctly decoded
            with m.If((self.opcode == Opcode.LUI) | (self.opcode == Opcode.AUIPC)):
                m.d.comb += [
                    Assert(self.r_type == 0b0),
                    Assert(self.i_type == 0b0),
                    Assert(self.s_type == 0b0),
                    Assert(self.b_type == 0b0),
                    Assert(self.u_type == 0b1),
                    Assert(self.j_type == 0b0),
                    Assert(~self.trap),
                    Assert(self.imm == u_imm),
                    Assert(self.format == Format.U_type)
                ]
            with m.Else():
                m.d.comb += Assert(self.u_type == 0b0)

            # Check if J-type instructions are correctly decoded
            with m.If((self.opcode == Opcode.JAL) | (self.opcode == Opcode.JALR)):
                m.d.comb += [
                    Assert(self.r_type == 0b0),
                    Assert(self.i_type == 0b0),
                    Assert(self.s_type == 0b0),
                    Assert(self.b_type == 0b0),
                    Assert(self.u_type == 0b0),
                    Assert(self.j_type == 0b1),
                    Assert(~self.trap),
                ]
                with m.If(self.opcode == Opcode.JAL):
                    m.d.comb += Assert(self.format == Format.J_type)
                    m.d.comb += Assert(self.imm == j_imm)
                with m.Else():
                    m.d.comb += Assert(self.format == Format.I_type)
                    m.d.comb += Assert(self.imm == i_imm)
            with m.Else():
                m.d.comb += Assert(self.j_type == 0b0)

        return m


if __name__ == "__main__":
    m = Module()
    formal = True
    m.submodules.decoder = decoder = Decoder(xlen=XLEN.RV32, formal=formal)

    def bench():
        # ADDI R31 = R1 + (-1)
        yield decoder.instr.eq(0b1111_1111_1111_00001_000_11111_0010011)
        yield Settle()

        assert ((yield decoder.format) == (Format.I_type.value))
        assert (yield decoder.i_type)
        assert not (yield decoder.trap)

        # yield decoder.instr.eq(-1)
        # yield Settle()
        # assert (yield decoder.trap)

    if not formal:
        sim = Simulator(decoder)
        sim.add_process(bench)
        with sim.write_vcd("decoder.vcd"):
            sim.run()

    with open("decoder.v", "w") as file:
        file.write(verilog.convert(m, ports=decoder.ports()))