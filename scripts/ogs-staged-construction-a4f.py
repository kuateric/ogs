#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4F: a freshly activated material has no constitutive history before its
# placement instant. A4C correctly rebases the current displacement to the
# placement configuration, but using (u_prev - u_placement) for the previous
# constitutive strain still imports deformation from the previously inactive
# domain. During the birth physical timestep the constitutive previous
# displacement must therefore be exactly zero in placement-relative
# coordinates. After that timestep the ordinary relative history resumes.

la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")

old = """        activation_reference_displacement_.resize(0);
        activation_reference_pending_ = true;
    }
"""
new = """        activation_reference_displacement_.resize(0);
        activation_reference_pending_ = true;
        activation_birth_step_ = true;
    }
"""
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4C activation reference initialization")
text = text.replace(old, new)

anchor = """    Eigen::VectorXd activationRelativeDisplacement(
        Eigen::Ref<Eigen::VectorXd const> const u) const
    {
        if (activation_reference_displacement_.size() == 0)
        {
            return u;
        }
        if (activation_reference_displacement_.size() != u.size())
        {
            OGS_FATAL(
                "Activation placement reference size does not match local "
                "displacement size.");
        }
        return u - activation_reference_displacement_;
    }

"""
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A4C activation relative-displacement helper")
addition = anchor + """    Eigen::VectorXd activationPreviousRelativeDisplacement(
        Eigen::Ref<Eigen::VectorXd const> const u_prev) const
    {
        if (activation_birth_step_ &&
            activation_reference_displacement_.size() != 0)
        {
            // The material did not exist in the previous physical state. Its
            // constitutive predecessor is the stress-free birth
            // configuration, not the displacement field left in the inactive
            // mesh region.
            return Eigen::VectorXd::Zero(u_prev.size());
        }
        return activationRelativeDisplacement(u_prev);
    }

    void completeActivationBirthStep()
    {
        activation_birth_step_ = false;
    }

"""
text = text.replace(anchor, addition)

old = """    bool activation_reference_pending_ = false;
    Eigen::VectorXd activation_reference_displacement_;
"""
new = """    bool activation_reference_pending_ = false;
    bool activation_birth_step_ = false;
    Eigen::VectorXd activation_reference_displacement_;
"""
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4C activation reference members")
la.write_text(text.replace(old, new), encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")

old = """        Eigen::VectorXd const u_prev_constitutive =
            this->activationRelativeDisplacement(u_prev);
"""
new = """        Eigen::VectorXd const u_prev_constitutive =
            this->activationPreviousRelativeDisplacement(u_prev);
"""
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4C assembly previous-displacement mapping")
text = text.replace(old, new)

old = """        Eigen::VectorXd const local_x_prev_constitutive =
            this->activationRelativeDisplacement(local_x_prev);
"""
new = """        Eigen::VectorXd const local_x_prev_constitutive =
            this->activationPreviousRelativeDisplacement(local_x_prev);
"""
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4C postTimestep previous-displacement mapping")
text = text.replace(old, new)

old = """        for (unsigned ip = 0; ip < n_integration_points; ip++)
        {
            this->prev_states_[ip] = this->current_states_[ip];
        }
    }

    std::vector<double> const& getMaterialForces(
"""
new = """        for (unsigned ip = 0; ip < n_integration_points; ip++)
        {
            this->prev_states_[ip] = this->current_states_[ip];
        }

        // From the next physical timestep onward this material has a genuine
        // previous constitutive state and ordinary placement-relative history
        // applies.
        this->completeActivationBirthStep();
    }

    std::vector<double> const& getMaterialForces(
"""
if text.count(old) != 1:
    raise RuntimeError("Unexpected SmallDeformation postTimestep completion anchor")
fem.write_text(text.replace(old, new), encoding="utf-8")

print("Applied OGS Staged Construction A4F zero constitutive pre-history at placement")
