import gpytorch
import torch
from torch.autograd import Variable
from .grid_inducing_point_module import GridInducingPointModule
from ..lazy import NonLazyVariable, SumInterpolatedLazyVariable
from ..random_variables import GaussianRandomVariable
from ..variational import GridInducingPointStrategy
from ..utils import left_interp


class AdditiveGridInducingPointModule(GridInducingPointModule):
    def _compute_grid(self, inputs):
        n_data, n_components, n_dimensions = inputs.size()
        inputs = inputs.transpose(0, 1).contiguous().view(n_components * n_data, n_dimensions)
        interp_indices, interp_values = super(AdditiveGridInducingPointModule, self)._compute_grid(inputs)
        interp_indices = interp_indices.view(n_components, n_data, -1)
        interp_values = interp_values.view(n_components, n_data, -1)
        return interp_indices, interp_values

    def __call__(self, inputs, **kwargs):
        if inputs.ndimension() == 1:
            inputs = inputs.unsqueeze(-1).unsqueeze(-1)
        elif inputs.ndimension() == 2:
            inputs = inputs.unsqueeze(-1)
        elif inputs.ndimension() != 3:
            raise RuntimeError('AdditiveGridInducingPointModule expects a 3d tensor.')

        n_data, n_components, n_dimensions = inputs.size()
        if n_dimensions != len(self.grid_bounds):
            raise RuntimeError('The number of dimensions should match the inducing points number of dimensions.')
        if n_dimensions != 1:
            raise RuntimeError('At the moment, AdditiveGridInducingPointModule only supports 1d'
                               ' (Toeplitz) interpolation.')

        if self.exact_inference:
            if self.conditioning:
                interp_indices, interp_values = self._compute_grid(inputs)
                self.train_interp_indices = interp_indices
                self.train_interp_values = interp_values
            else:
                train_data = self.train_inputs[0].data if hasattr(self, 'train_inputs') else None
                if train_data is not None and torch.equal(inputs.data, train_data):
                    interp_indices = self.train_interp_indices
                    interp_values = self.train_interp_values
                else:
                    interp_indices, interp_values, = self._compute_grid(inputs)

            induc_output = gpytorch.Module.__call__(self, Variable(self._inducing_points))
            if not isinstance(induc_output, GaussianRandomVariable):
                raise RuntimeError('Output should be a GaussianRandomVariable')

            # Compute test mean
            # Left multiply samples by interpolation matrix
            interp_indices = Variable(interp_indices)
            interp_values = Variable(interp_values)
            mean = left_interp(interp_indices, interp_values, induc_output.mean()).sum(0)

            # Compute test covar
            base_lv = induc_output.covar()
            covar = SumInterpolatedLazyVariable(base_lv, interp_indices, interp_values, interp_indices, interp_values)

            return GaussianRandomVariable(mean, covar)

        else:
            variational_mean = self.variational_mean
            chol_variational_covar = self.chol_variational_covar
            induc_output = gpytorch.Module.__call__(self, Variable(self._inducing_points))
            interp_indices, interp_values = self._compute_grid(inputs)

            # Initialize variational parameters, if necessary
            if not self.variational_params_initialized[0]:
                mean_init = induc_output.mean().data
                chol_covar_init = torch.eye(len(mean_init)).type_as(mean_init)
                variational_mean.data.copy_(mean_init)
                chol_variational_covar.data.copy_(chol_covar_init)
                self.variational_params_initialized.fill_(1)

            # Calculate alpha vector
            if self.training:
                alpha = induc_output.mean()
            else:
                if not self.has_computed_alpha[0]:
                    alpha = variational_mean.sub(induc_output.mean())
                    self.alpha.copy_(alpha.data)
                    self.has_computed_alpha.fill_(1)
                else:
                    alpha = Variable(self.alpha)

            # Compute test mean
            # Left multiply samples by interpolation matrix
            interp_indices = Variable(interp_indices)
            interp_values = Variable(interp_values)
            test_mean = left_interp(interp_indices, interp_values, alpha).sum(0)

            # Compute test covar
            if self.training:
                base_lv = induc_output.covar()
            else:
                base_lv = NonLazyVariable(self.variational_covar)
            test_covar = SumInterpolatedLazyVariable(base_lv, interp_indices, interp_values,
                                                     interp_indices, interp_values)

            output = GaussianRandomVariable(test_mean, test_covar)

            # Add variational strategy
            if self.training:
                output._variational_strategy = GridInducingPointStrategy(variational_mean,
                                                                         chol_variational_covar,
                                                                         induc_output)

        if not isinstance(output, GaussianRandomVariable):
            raise RuntimeError('Output should be a GaussianRandomVariable')

        return output