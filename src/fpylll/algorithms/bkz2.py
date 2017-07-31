# -*- coding: utf-8 -*-

from random import randint
from fpylll import BKZ, Enumeration, EnumerationError
from fpylll.algorithms.bkz import BKZReduction as BKZBase
from fpylll.algorithms.bkz_stats import dummy_tracer
from fpylll.util import gaussian_heuristic


class BKZReduction(BKZBase):

    def __init__(self, A):
        """Create new BKZ object.

        :param A: an integer matrix, a GSO object or an LLL object

        """
        BKZBase.__init__(self, A)

    def get_pruning(self, kappa, block_size, params, tracer=dummy_tracer):
        strategy = params.strategies[block_size]
        radius = self.M.get_r(kappa, kappa) * self.lll_obj.delta
        r = [self.M.get_r(i, i) for i in range(kappa, kappa+block_size)]
        gh_radius = gaussian_heuristic(r)

        if (params.flags & BKZ.GH_BND and block_size > 30):
            radius = min(radius, gh_radius * params.gh_factor)

        return radius, strategy.get_pruning(radius, gh_radius)

    def randomize_block(self, min_row, max_row, tracer=dummy_tracer, density=0):
        """Randomize basis between from ``min_row`` and ``max_row`` (exclusive)

            1. permute rows

            2. apply lower triangular matrix with coefficients in -1,0,1

            3. LLL reduce result

        :param min_row: start in this row
        :param max_row: stop at this row (exclusive)
        :param tracer: object for maintaining statistics
        :param density: number of non-zero coefficients in lower triangular transformation matrix
        """
        if max_row - min_row < 2:
            return  # there is nothing to do

        # 1. permute rows
        niter = 4 * (max_row-min_row)  # some guestimate
        with self.M.row_ops(min_row, max_row):
            for i in range(niter):
                b = a = randint(min_row, max_row-1)
                while b == a:
                    b = randint(min_row, max_row-1)
                self.M.move_row(b, a)

        # 2. triangular transformation matrix with coefficients in -1,0,1
        with self.M.row_ops(min_row, max_row):
            for a in range(min_row, max_row-2):
                for i in range(density):
                    b = randint(a+1, max_row-1)
                    s = randint(0, 1)
                    self.M.row_addmul(a, b, 2*s-1)

        return

    def svp_preprocessing(self, kappa, block_size, params, tracer=dummy_tracer):
        clean = True

        clean &= BKZBase.svp_preprocessing(self, kappa, block_size, params, tracer)

        for preproc in params.strategies[block_size].preprocessing_block_sizes:
            prepar = params.__class__(block_size=preproc, strategies=params.strategies, flags=BKZ.GH_BND)
            clean &= self.tour(prepar, kappa, kappa + block_size, tracer=tracer)

        return clean

    def svp_reduction(self, kappa, block_size, params, tracer=dummy_tracer):
        """

        :param kappa:
        :param block_size:
        :param params:
        :param tracer:

        """

        self.lll_obj.size_reduction(0, kappa+1)
        old_first, old_first_expo = self.M.get_r_exp(kappa, kappa)

        remaining_probability, rerandomize = 1.0, False

        while remaining_probability > 1. - params.min_success_probability:
            with tracer.context("preprocessing"):
                if rerandomize:
                    with tracer.context("randomization"):
                        self.randomize_block(kappa+1, kappa+block_size,
                                             density=params.rerandomization_density, tracer=tracer)
                with tracer.context("reduction"):
                    self.svp_preprocessing(kappa, block_size, params, tracer=tracer)

            with tracer.context("pruner"):
                radius, pruning = self.get_pruning(kappa, block_size, params, tracer)

            try:
                enum_obj = Enumeration(self.M)
                with tracer.context("enumeration",
                                    enum_obj=enum_obj,
                                    probability=pruning.expectation,
                                    full=block_size==params.block_size):
                    solution, max_dist = enum_obj.enumerate(kappa, kappa + block_size, radius, 0,
                                                            pruning=pruning.coefficients)[0]
                with tracer.context("postprocessing"):
                    self.svp_postprocessing(kappa, block_size, solution, tracer=tracer)
                rerandomize = False

            except EnumerationError:
                rerandomize = True

            remaining_probability *= (1 - pruning.expectation)

        self.lll_obj.size_reduction(0, kappa+1)
        new_first, new_first_expo = self.M.get_r_exp(kappa, kappa)

        clean = old_first <= new_first * 2**(new_first_expo - old_first_expo)
        return clean
