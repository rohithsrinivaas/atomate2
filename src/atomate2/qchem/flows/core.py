# insert makers for flows
# reference: https://github.com/hrushikesh-s/atomate2/tree/hiphive/src/atomate2/vasp/flows
# Try Double Relax

"""Core Qchem flows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from emmet.core.qchem.calculation import Calculation
from jobflow import Flow, Maker

from atomate2.qchem.jobs.core import (  
    SinglePointMaker,
    OptMaker,
    ForceMaker,
    TransitionStateMaker,
    FreqMaker,
)
from atomate2.qchem.sets.core import (
    SinglePointSetGenerator,
    OptSetGenerator,
    ForceSetGenerator,
    TransitionStateSetGenerator,
    FreqSetGenerator,
)

if TYPE_CHECKING:
    from pathlib import Path

    from jobflow import Job
    from pymatgen.core.structure import Molecule 

    from atomate2.qchem.jobs.base import BaseQCMaker

import numpy as np

@dataclass
class DoubleOptMaker(Maker):
    """
    Maker to perform a double Qchem relaxation.

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    relax_maker1 : .BaseVaspMaker
        Maker to use to generate the first relaxation.
    relax_maker2 : .BaseVaspMaker
        Maker to use to generate the second relaxation.
    """

    name: str = "double opt"
    opt_maker1: BaseQCMaker | None = field(default_factory=OptMaker)
    opt_maker2: BaseQCMaker = field(default_factory=OptMaker)

    def make(self, molecule: Molecule, prev_dir: str | Path | None = None) -> Flow:
        """
        Create a flow with two chained molecular optimizations.

        Parameters
        ----------
        molecule : .Molecule
            A pymatgen Molecule object.
        prev_dir : str or Path or None
            A previous QChem calculation directory to copy output files from.

        Returns
        -------
        Flow
            A flow containing two geometric optimizations.
        """
        jobs: list[Job] = []
        if self.opt_maker1:
            # Run a pre-relaxation
            opt1 = self.opt_maker1.make(molecule, prev_dir=prev_dir)
            opt1.name += " 1"
            jobs += [opt1]
            molecule = opt1.output.optimized_molecule
            prev_dir = opt1.output.dir_name

        opt2 = self.opt_maker2.make(molecule, prev_dir=prev_dir)
        opt2.name += " 2"
        jobs += [opt2]

        return Flow(jobs, output=opt2.output, name=self.name)

    @classmethod
    def from_opt_maker(cls, opt_maker: BaseQCMaker) -> DoubleOptMaker:
        """
        Instantiate the DoubleRelaxMaker with two relax makers of the same type.

        Parameters
        ----------
        opt_maker : .BaseQCMaker
            Maker to use to generate the first and second geometric optimizations.
        """
        return cls(
            relax_maker1=deepcopy(opt_maker), relax_maker2=deepcopy(opt_maker)
        )



@dataclass
class FrequencyOptMaker(Maker):
    """
    Maker to perform a frequency calculation after an optimization.
    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    opt_maker : .BaseQCMaker
        Maker to use to generate the opt maker
    freq_maker : .BaseQCMaker
        Maker to use to generate the freq maker
    """

    name: str = "frequency flattening opt"
    opt_maker: BaseQCMaker = field(default_factory=OptMaker)
    freq_maker: BaseQCMaker = field(default_factory= FreqMaker)

    def make(self, molecule: Molecule, prev_dir: str | Path | None = None) -> Flow:
        """
        Create a flow with optimization followed by frequency calculation.

        Parameters
        ----------
        molecule : .Molecule
            A pymatgen Molecule object.
        prev_dir : str or Path or None
            A previous QChem calculation directory to copy output files from.

        Returns
        -------
        Flow
            A flow containing with optimization and frequency calculation.
        """
        jobs: list[Job] = []
        opt = self.opt_maker.make(molecule, prev_dir=prev_dir)
        opt.name += " 1"
        jobs += [opt]
        molecule = opt.output.optimized_molecule
        prev_dir = opt.output.dir_name


        freq = self.freq_maker.make(molecule, prev_dir=prev_dir)
        freq.name += " 1"
        jobs += [freq]
        modes = freq.output.calcs_reversed[0].output.frequency_modes
        frequencies = freq.output.calcs_reversed[0].output.frequencies

        return Flow(jobs, output={'opt': opt.output, 'freq':freq.output},name=self.name)


@dataclass
class FrequencyOptFlatteningMaker(Maker):
    """
    Maker to perform a frequency calculation after an optimization.
    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    opt_maker : .BaseQCMaker
        Maker to use to generate the opt maker
    freq_maker : .BaseQCMaker
        Maker to use to generate the freq maker
    """

    name: str = "frequency flattening opt"
    opt_maker: BaseQCMaker = field(default_factory=OptMaker)
    freq_maker: BaseQCMaker = field(default_factory= FreqMaker)
    scale: float = 1.0
    max_ffopt_runs: int = 10

    def make(self, molecule: Molecule, prev_dir: str | Path | None = None) -> Flow:
        """
        Create a flow with optimization followed by frequency calculation with perturbation along the negative frequency mode

        Parameters
        ----------
        molecule : .Molecule
            A pymatgen Molecule object.
        prev_dir : str or Path or None
            A previous QChem calculation directory to copy output files from.

        Returns
        -------
        Flow
            A flow containing with optimization and frequency calculation.
        """
        jobs: list[Job] = []
        opt = self.opt_maker.make(molecule, prev_dir=prev_dir)
        opt.name += " 1"
        jobs += [opt]
        molecule = opt.output.optimized_molecule
        prev_dir = opt.output.dir_name


        freq = self.freq_maker.make(molecule, prev_dir=prev_dir)
        freq.name += " 1"
        jobs += [freq]
        modes = freq.output.calcs_reversed[0].output.frequency_modes
        frequencies = freq.output.calcs_reversed[0].output.frequencies
        ffopt_runs = 1
        
        while frequencies[0] < 0 and ffopt_runs < self.max_ffopt_runs:
            mode = modes[0]
            molecule_copy = deepcopy(molecule)
            for ii in range(molecule):
                vec = np.array(mode[ii])
                molecule_copy.translate_sites(indices=[ii], vector=vec * self.get("scale", 1.0))
            molecule = molecule_copy
            
            ffopt_runs += 1
            opt = self.opt_maker.make(molecule, prev_dir=prev_dir)
            opt.name += f" {ffopt_runs}"
            jobs += [opt]
            molecule = opt.output.optimized_molecule
            prev_dir = opt.output.dir_name

            freq = self.freq_maker.make(molecule, prev_dir=prev_dir)
            freq.name += f" {ffopt_runs}"
            jobs += [freq]
            modes = freq.output.calcs_reversed[0].output.frequency_modes
            frequencies = freq.output.calcs_reversed[0].output.frequencies
            
        return Flow(jobs, output={'opt_latest': opt.output, 'freq_latest':freq.output},name=self.name)
