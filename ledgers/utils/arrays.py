from typing import Sequence


def is_homogenous(seq: Sequence) -> bool:
    """Checks if a sequence is homogenous.

    :param seq: Mapping

    :raises:
        ValueError: if seq is not valid for test.

    :return: True if homogenous else False
    :rtype: bool
    """

    try:
        first_type = type(seq[0])
    except (KeyError, TypeError) as e:
        raise ValueError(f'Sequence {seq} is not valid for homogeneity test. Exception raised: {e}')

    return all(type(item) == first_type for item in seq)
