import pytest

from harness.pilot_mix_recipes import verify_definitions


SEED = "3,2,1,1,50,0,g,w,m2,z0,xa0,xb0,d0,o0,u1,cm0"
RATIO = SEED.replace("u1", "u3")
GRADIENT = "3,2,1,1,50,0,g,w,m0,z2,xa0,xb0,d0,o0,u2,cm3,r1/0.8000/0.2000"
SAVED = ";".join((SEED, RATIO, GRADIENT))


def test_mix_requires_two_new_modes_and_preserves_seed():
    assert verify_definitions(SEED, SAVED, SAVED) == ["u2", "u3"]
    with pytest.raises(ValueError, match="mix_definition_persistence"):
        verify_definitions(SEED, ";".join((SEED, GRADIENT)), ";".join((SEED, GRADIENT)))
    with pytest.raises(ValueError, match="mix_definition_persistence"):
        verify_definitions(SEED, SAVED, SEED)
    with pytest.raises(ValueError, match="mix_definition_identity"):
        verify_definitions(SEED, SAVED.replace("u3", "u1"), SAVED)
