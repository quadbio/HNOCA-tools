from functools import partial

import jax
import numba
import pandas as pd
import yaml
from jax import numpy as jnp


def to_jax_array(x):
    """Turn matrix to jax array."""
    if hasattr(x, "todense"):
        # Currently this is not supported for really large matrices
        # return BCOO.from_scipy_sparse(x).update_layout(n_batch=1, on_inefficient=None)
        return jnp.asarray(x.todense())
    else:
        return jnp.asarray(x)


@jax.jit
@partial(jax.vmap, in_axes=[None, 0])
def masked_max(x, mask):  # noqa D103
    return jnp.max(x * mask, axis=1)


@jax.jit
@partial(jax.vmap, in_axes=[None, 0])
def masked_mean(x, mask):  # noqa D103
    return jnp.sum(x * mask, axis=1) / jnp.sum(mask)


def frac_nonzero(x, axis=0):  # noqa D103
    return jnp.mean(x > 0, axis=axis)


jit_frac_nonzero = jax.jit(frac_nonzero)


def dict_to_binary(d):
    """Convert dictionary to binary matrix."""
    df = pd.concat(
        [pd.Series(v, name=k).astype(str) for k, v in d.items()],
        axis=1,
    )
    marker_mat = pd.get_dummies(df.stack()).groupby(level=1).sum().clip(upper=1)
    return marker_mat


@numba.jit
def match(a, b):  # noqa D103
    return [b.index(x) if x in b else None for x in a]


def get_expr(adata, features=None, layer=None):
    """Get expression matrix from adata object"""
    if features is not None:
        # intersect with adata features
        features = list(set(features) & set(adata.var_names))
        adata = adata[
            :,
            match(numba.typed.List(features), numba.typed.List(adata.var_names.tolist())),
        ]
    else:
        features = adata.var_names.copy().tolist()

    if layer is not None:
        expr = to_jax_array(adata.layers[layer])
    else:
        expr = to_jax_array(adata.X)

    return expr, features


def get_markers(x):
    """Get marker genes from a dictionary."""
    return {n: v["marker_genes"] for n, v in x.items()}


def read_yaml(file):
    """Read yaml file."""
    with open(file) as f:
        marker_dict = yaml.safe_load(f)
    return marker_dict


def get_annot_df(x, group_name, min_expr=0.1):
    """Get valid annots from each level."""
    annot_list = []
    for _k, v in x.items():
        annot = v.set_index(group_name)["class"]
        if min_expr > 0:
            expr = v.set_index(group_name)["expr"]
            annot = annot[expr > min_expr]
        annot_list.append(annot)
    # Concat annots
    annot_df = pd.concat(annot_list, axis=1)
    # Rename cols to levels
    annot_df.columns = [str(i) for i in x.keys()]
    return annot_df


def matrix_to_long_df(x, features, groups):
    """Converts a matrix to a long dataframe"""
    df = pd.DataFrame(x, index=groups, columns=features)
    df = df.stack().reset_index()
    df.columns = ["group", "feature", "value"]
    return df


def marker_dict_depth(marker_hierarchy: dict) -> int:
    """
    Recursively compute the depth of a marker hierarchy dictionary.

    A marker hierarchy with no subtypes has a depth of 1.

    Args:
        marker_hierarchy: A dictionary where each key is a cell type and its value is
            a dict that must contain a 'marker_genes' key and can optionally contain a
            'subtypes' key (which is another marker hierarchy dict).

    Returns
    -------
        int: The maximum depth of the hierarchy.
    """
    max_depth = 0
    for _cell_type, data in marker_hierarchy.items():
        # Start with current level
        depth = 1
        # If there are subtypes, add their depth recursively
        if "subtypes" in data and isinstance(data["subtypes"], dict):
            depth += marker_dict_depth(data["subtypes"])
        max_depth = max(max_depth, depth)
    return max_depth
