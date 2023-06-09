# Chefer H, Gur S, Wolf L. Transformer interpretability beyond attention visualization[C]
# //Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition. 2021: 782-791.

import torch
import torch.nn as nn
import torch.nn.functional as F

__all__ = ['forward_hook', 'Clone', 'Add', 'Cat', 'safe_divide', 'einsum', 'IndexSelect', 'AddEye',
           'ReLU', 'GELU', 'ELU', 'Softmax', 'Dropout', 'BatchNorm2d', 'BatchNorm3d', 'LayerNorm',
           'Linear',
           'MaxPool2d', 'MaxPool3d', 'AdaptiveAvgPool2d', 'AvgPool2d', 'Conv2d', 'Conv3d',
           'Sequential']


def safe_divide(a, b):
    den = b.clamp(min=1e-9) + b.clamp(max=1e-9)  # set the min bound, means get larger than 1e-9, the "stabilizer"
    den = den + den.eq(0).type(den.type()) * 1e-9  # if den==0 then +1*1e-9
    return a / den * b.ne(0).type(b.type())  # do / if b=!0 or *0


def forward_hook(self, inputs, output):
    try:
        if type(inputs[0]) in (list, tuple):
            self.X = []
            for i in inputs[0]:
                x = i.detach()
                x.requires_grad = True
                self.X.append(x)
        else:
            self.X = inputs[0].detach()
            self.X.requires_grad = True
    except IndexError as e:
        print(e)
        # print(numpy.shape(input), '\n', input)
        # print(numpy.shape(output), '\n', output)
        # self.X = input[0].detach()
        # self.X.requires_grad = True
        print('Error in forward_hook', inputs)
    self.Y = output


def backward_hook(self, grad_input, grad_output):
    self.grad_input = grad_input
    self.grad_output = grad_output


class RelProp(nn.Module):  # Deep TayLor Decomposition
    def __init__(self):
        super(RelProp, self).__init__()
        # if not self.training:
        self.register_forward_hook(forward_hook)

    def gradprop(self, Z, X, S):
        """torch.autograd.grad(outputs, inputs, grad_outputs=None, retain_graph=None)
        Computes and returns the sum of gradients of outputs with respect to the inputs.
        Z.shape = S.shape like [b, t, d]
        C.shape = X.shape like [b, t, d] or list([b, t, d], ) if belongs torch some op like addition/multiple
        """
        C = torch.autograd.grad(Z, X, S, retain_graph=True)
        # print('Z', Z.shape)  [1, 56, 40]
        # print('S', S.shape)  [1, 56, 40]
        # print('C', len(C), C[0].shape)  [1, 56, 40]
        # print('X', len(X), X[0].shape)  [1, 56, 40]
        return C

    def relprop(self, R, alpha):
        return R


class RelPropSimple(RelProp):
    def relprop(self, R, alpha):
        Z = self.forward(self.X)
        S = safe_divide(R, Z)
        C = self.gradprop(Z, self.X, S)

        if not torch.is_tensor(self.X):
            outputs = []
            outputs.append(self.X[0] * C[0])
            outputs.append(self.X[1] * C[1])
        else:
            outputs = self.X * (C[0])
        return outputs


class AddEye(RelPropSimple):
    # input of shape B, C, seq_len, seq_len
    def forward(self, input):
        return input + torch.eye(input.shape[2]).expand_as(input).to(input.device)


class ReLU(nn.ReLU, RelProp):
    pass


class ELU(nn.ELU, RelProp):
    pass


class GELU(nn.GELU, RelProp):
    pass


class Softsign(nn.Softsign, RelProp):
    # TODO +- activation respectively
    pass


class Sigmoid(nn.Sigmoid, RelProp):
    pass


class Softmax(nn.Softmax, RelProp):
    pass


class LayerNorm(nn.LayerNorm, RelProp):
    pass


class Dropout(nn.Dropout, RelProp):
    pass


class MaxPool2d(nn.MaxPool2d, RelPropSimple):
    pass


class MaxPool3d(nn.MaxPool3d, RelPropSimple):
    pass


class AdaptiveAvgPool2d(nn.AdaptiveAvgPool2d, RelPropSimple):
    pass


class AvgPool2d(nn.AvgPool2d, RelPropSimple):
    pass


class Add(RelPropSimple):
    def forward(self, inputs):
        return torch.add(*inputs)

    def relprop(self, R, alpha):
        Z = self.forward(self.X)
        S = safe_divide(R, Z)
        C = self.gradprop(Z, self.X, S)

        a = self.X[0] * C[0]
        b = self.X[1] * C[1]

        a_sum = a.sum()
        b_sum = b.sum()

        a_fact = safe_divide(a_sum.abs(), a_sum.abs() + b_sum.abs()) * R.sum()
        b_fact = safe_divide(b_sum.abs(), a_sum.abs() + b_sum.abs()) * R.sum()

        a = a * safe_divide(a_fact, a.sum())
        b = b * safe_divide(b_fact, b.sum())

        outputs = [a, b]

        return outputs


class einsum(RelPropSimple):
    def __init__(self, equation):
        super().__init__()
        self.equation = equation

    def forward(self, *operands):
        return torch.einsum(self.equation, *operands)


# class IndexSelect(RelProp):
#     def forward(self, inputs, dim, indices):
#         self.__setattr__('dim', dim)
#         self.__setattr__('indices', indices)
#
#         return torch.index_select(inputs, dim, indices)
#
#     def relprop(self, R, alpha):
#         # Z = self.forward(self.X, self.dim, self.indices)
#         Z = torch.index_select(self.X, self.dim, self.indices)
#         S = safe_divide(R, Z)
#         C = self.gradprop(Z, self.X, S)
#
#         if torch.is_tensor(self.X) == False:
#             outputs = []
#             outputs.append(self.X[0] * C[0])
#             outputs.append(self.X[1] * C[1])
#         else:
#             outputs = self.X * (C[0])
#         return outputs


class IndexSelect(nn.Module):

    def forward(self, inputs, dim, indices):
        self.__setattr__('dim', dim)
        self.__setattr__('indices', indices)
        self.X = inputs.detach()
        self.X.requires_grad = True
        self.Y = torch.index_select(input=inputs, dim=dim, index=indices)
        return self.Y

    def relprop(self, R, alpha):
        # Z = self.forward(inputs=self.X, dim=self.dim, indices=self.indices)
        Z = torch.index_select(self.X, self.dim, self.indices)
        S = safe_divide(R, Z)
        C = self.gradprop(Z, self.X, S)

        if torch.is_tensor(self.X) is False:
            outputs = [self.X[0] * C[0], self.X[1] * C[1]]
        else:
            outputs = self.X * (C[0])
        return outputs

    def gradprop(self, Z, X, S):
        C = torch.autograd.grad(Z, X, S, retain_graph=True)
        return C


class Clone(RelProp):
    def forward(self, input, num):
        self.__setattr__('num', num)
        outputs = []
        for _ in range(num):
            outputs.append(input)

        return outputs

    def relprop(self, R, alpha):
        Z = []
        for _ in range(self.num):
            Z.append(self.X)
        S = [safe_divide(r, z) for r, z in zip(R, Z)]
        C = self.gradprop(Z, self.X, S)[0]

        R = self.X * C

        return R


class Cat(RelProp):
    def forward(self, inputs, dim):
        self.__setattr__('dim', dim)
        return torch.cat(inputs, dim)

    def relprop(self, R, alpha):
        Z = self.forward(self.X, self.dim)
        S = safe_divide(R, Z)
        C = self.gradprop(Z, self.X, S)

        outputs = []
        for x, c in zip(self.X, C):
            outputs.append(x * c)

        return outputs


class Sequential(nn.Sequential):
    def relprop(self, R, alpha):
        for m in reversed(self._modules.values()):
            R = m.relprop(R, alpha)
        return R


class BatchNorm2d(nn.BatchNorm2d, RelProp):
    def relprop(self, R, alpha):
        X = self.X
        beta = 1 - alpha
        weight = self.weight.unsqueeze(0).unsqueeze(2).unsqueeze(3) / (
            (self.running_var.unsqueeze(0).unsqueeze(2).unsqueeze(3).pow(2) + self.eps).pow(0.5))
        Z = X * weight + 1e-9
        S = R / Z
        Ca = S * weight
        R = self.X * (Ca)
        return R


class BatchNorm3d(nn.BatchNorm3d, RelProp):
    def relprop(self, R, alpha):
        X = self.X
        beta = 1 - alpha
        weight = self.weight.unsqueeze(0).unsqueeze(2).unsqueeze(3).unsqueeze(4) / (
            (self.running_var.unsqueeze(0).unsqueeze(2).unsqueeze(3).unsqueeze(4).pow(2) + self.eps).pow(0.5))
        Z = X * weight + 1e-9
        S = R / Z
        Ca = S * weight
        R = self.X * (Ca)
        return R


class Linear(nn.Linear, RelProp):
    def relprop(self, R, alpha):
        beta = alpha - 1
        pw = torch.clamp(self.weight, min=0)  # positive w
        nw = torch.clamp(self.weight, max=0)  # negative
        px = torch.clamp(self.X, min=0)  # positive x
        nx = torch.clamp(self.X, max=0)  # negative

        def f(w1, w2, x1, x2):
            Z1 = F.linear(x1, w1)  #
            Z2 = F.linear(x2, w2)  #
            S1 = safe_divide(R, Z1 + Z2)  # R/Zj
            S2 = safe_divide(R, Z1 + Z2)  # R/Zj
            # grad_outputs: “vector” in the vector-Jacobian product for each x
            # https://blog.csdn.net/waitingwinter/article/details/105774720 for more details
            C1 = x1 * torch.autograd.grad(outputs=Z1, inputs=x1, grad_outputs=S1)[0]  # d(Z1)/d(X1) * S1
            C2 = x2 * torch.autograd.grad(Z2, x2, S2)[0]

            return C1 + C2

        activator_relevances = f(pw, nw, px, nx)  # Z1:++, Z2:--
        inhibitor_relevances = f(nw, pw, px, nx)  # Z1:+-, Z2:-+

        R = alpha * activator_relevances - beta * inhibitor_relevances

        return R


class Conv2d(nn.Conv2d, RelProp):
    def gradprop2(self, DY, weight):
        Z = self.forward(self.X)

        output_padding = self.X.size()[2] - (
                (Z.size()[2] - 1) * self.stride[0] - 2 * self.padding[0] + self.kernel_size[0])

        return F.conv_transpose2d(DY, weight, stride=self.stride, padding=self.padding, output_padding=output_padding)

    def relprop(self, R, alpha):
        if self.X.shape[1] == 3:  # RGB
            pw = torch.clamp(self.weight, min=0)
            nw = torch.clamp(self.weight, max=0)
            X = self.X
            L = self.X * 0 + \
                torch.min(torch.min(torch.min(self.X, dim=1, keepdim=True)[0], dim=2, keepdim=True)[0], dim=3,
                          keepdim=True)[0]
            H = self.X * 0 + \
                torch.max(torch.max(torch.max(self.X, dim=1, keepdim=True)[0], dim=2, keepdim=True)[0], dim=3,
                          keepdim=True)[0]
            Za = torch.conv2d(X, self.weight, bias=None, stride=self.stride, padding=self.padding, groups=self.groups) - \
                 torch.conv2d(L, pw, bias=None, stride=self.stride, padding=self.padding, groups=self.groups) - \
                 torch.conv2d(H, nw, bias=None, stride=self.stride, padding=self.padding, groups=self.groups) + 1e-9

            S = R / Za
            C = X * self.gradprop2(S, self.weight) - L * self.gradprop2(S, pw) - H * self.gradprop2(S, nw)
            R = C
        else:
            beta = alpha - 1  # 0
            pw = torch.clamp(self.weight, min=0)
            nw = torch.clamp(self.weight, max=0)
            px = torch.clamp(self.X, min=0)
            nx = torch.clamp(self.X, max=0)

            def f(w1, w2, x1, x2):
                Za = F.conv2d(x1, w1, bias=None, stride=self.stride, padding=self.padding, groups=self.groups)
                Zb = F.conv2d(x2, w2, bias=None, stride=self.stride, padding=self.padding, groups=self.groups)
                S1 = safe_divide(R, Za)
                S2 = safe_divide(R, Zb)
                # print(R.sum())  # =1
                # This may break the relevance conservation due to: "almost all relevance is
                # absorbed by the non-redistributed zero-order term."
                Ca = x1 * self.gradprop(Za, x1, S1)[0]
                Cb = x2 * self.gradprop(Zb, x2, S2)[0]

                # Ca2 = torch.autograd.grad(Ca, x1, torch.ones_like(x1), retain_graph=True)[0]
                # Cb2 = torch.autograd.grad(Cb, x2, torch.ones_like(x2), retain_graph=True)[0]
                #
                # Ca3 = torch.autograd.grad(Ca2, x1, torch.ones_like(Ca2))[0]
                # Cb3 = torch.autograd.grad(Cb2, x2, torch.ones_like(Cb2))[0]

                # rate1 = safe_divide(Ca, Za)
                # rate2 = safe_divide(Cb, Zb)
                #
                # Ra = safe_divide(Ca, rate1*Za)*R
                # Rb = safe_divide(Cb, rate2*Zb)*R

                # print('sum: ', Ra.sum(), Rb.sum())
                return Ca + Cb

            activator_relevances = f(pw, nw, px, nx)  # Z1+++, Z2--+
            inhibitor_relevances = f(nw, pw, px, nx)  # Z1-+-, Z2+--

            R = alpha * activator_relevances - beta * inhibitor_relevances
        return R/2


class Conv3d(nn.Conv3d, RelProp):
    def relprop(self, R, alpha):
        beta = alpha - 1  # 0
        pw = torch.clamp(self.weight, min=0)
        nw = torch.clamp(self.weight, max=0)
        px = torch.clamp(self.X, min=0)
        nx = torch.clamp(self.X, max=0)

        def f(w1, w2, x1, x2):
            Za = F.conv3d(x1, w1, bias=None, stride=self.stride, padding=self.padding, groups=self.groups)
            Zb = F.conv3d(x2, w2, bias=None, stride=self.stride, padding=self.padding, groups=self.groups)
            S1 = safe_divide(R, Za)
            S2 = safe_divide(R, Zb)
            # print(R.sum())  # =1
            # This may break the relevance conservation due to: "almost all relevance is
            # absorbed by the non-redistributed zero-order term."
            Ca = x1 * self.gradprop(Za, x1, S1)[0]
            Cb = x2 * self.gradprop(Zb, x2, S2)[0]

            return Ca + Cb

        activator_relevances = f(pw, nw, px, nx)  # Z1+++, Z2--+
        inhibitor_relevances = f(nw, pw, px, nx)  # Z1-+-, Z2+--

        R = alpha * activator_relevances - beta * inhibitor_relevances
        return R/2
