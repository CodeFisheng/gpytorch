from torch.autograd import Variable
from .parameter_group import ParameterGroup
from ..random_variables import RandomVariable

class MCParameterGroup(ParameterGroup):
    def __init__():
        super(MCParameterGroup, self).__init__()
        self._priors = {}
        self._options['num_samples'] = 20

        for name, param in kwargs.items():
            var, prior = param
            if not isinstance(prior, RandomVariable):
                raise RuntimeError('All parameters in an MCParameterGroup must have a prior specified by a RandomVariable')

            if not isinstance(var, Variable):
                raise RuntimeError('All parameters in an MCParameterGroup must have an associated Variable')

            setattr(self,name,var)
            self._priors[name] = prior
            self._samples[name] = []


    def sample(self):
        raise NotImplementedError


    def has_converged(self,loss_closure):
        return True


