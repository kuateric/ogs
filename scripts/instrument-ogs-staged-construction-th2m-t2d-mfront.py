#!/usr/bin/env python3
from pathlib import Path

p = Path('MaterialLib/SolidModels/MFront/MFrontGeneric.h')
text = p.read_text(encoding='utf-8')

alloc = """    createMaterialStateVariables() const
    {
        return std::make_unique<MaterialStateVariablesMFront<DisplacementDim>>(
            equivalent_plastic_strain_offset_, _behaviour);
    }"""
alloc_probe = """    createMaterialStateVariables() const
    {
        INFO(\"TH2M-T2D MFront/MGIS fresh BehaviourData allocation\");
        return std::make_unique<MaterialStateVariablesMFront<DisplacementDim>>(
            equivalent_plastic_strain_offset_, _behaviour);
    }"""
if text.count(alloc) != 1:
    raise RuntimeError('canonical MFront state-allocation anchor changed')
text = text.replace(alloc, alloc_probe, 1)

init = """        auto& state =
            static_cast<MaterialStateVariablesMFront<DisplacementDim>&>(
                material_state_variables);

        auto const& ivs = getInternalVariables();"""
init_probe = """        auto& state =
            static_cast<MaterialStateVariablesMFront<DisplacementDim>&>(
                material_state_variables);
        INFO(\"TH2M-T2D MFront/MGIS virgin state initializer at t = {:g}\", t);

        auto const& ivs = getInternalVariables();"""
if text.count(init) != 1:
    raise RuntimeError('canonical MFront initializer anchor changed')
text = text.replace(init, init_probe, 1)

p.write_text(text, encoding='utf-8')
