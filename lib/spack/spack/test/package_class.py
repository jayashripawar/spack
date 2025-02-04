# Copyright 2013-2022 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

"""Test class methods on Package objects.

This doesn't include methods on package *instances* (like do_install(),
etc.).  Only methods like ``possible_dependencies()`` that deal with the
static DSL metadata for packages.
"""

import os
import shutil

import pytest

import llnl.util.filesystem as fs

import spack.package_base
import spack.repo


@pytest.fixture(scope="module")
def mpi_names(mock_repo_path):
    return [spec.name for spec in mock_repo_path.providers_for("mpi")]


@pytest.fixture()
def mpileaks_possible_deps(mock_packages, mpi_names):
    possible = {
        "callpath": set(["dyninst"] + mpi_names),
        "low-priority-provider": set(),
        "dyninst": set(["libdwarf", "libelf"]),
        "fake": set(),
        "libdwarf": set(["libelf"]),
        "libelf": set(),
        "mpich": set(),
        "mpich2": set(),
        "mpileaks": set(["callpath"] + mpi_names),
        "multi-provider-mpi": set(),
        "zmpi": set(["fake"]),
    }
    return possible


def test_possible_dependencies(mock_packages, mpileaks_possible_deps):
    pkg_cls = spack.repo.path.get_pkg_class("mpileaks")
    expanded_possible_deps = pkg_cls.possible_dependencies(expand_virtuals=True)
    assert mpileaks_possible_deps == expanded_possible_deps
    assert {
        "callpath": {"dyninst", "mpi"},
        "dyninst": {"libdwarf", "libelf"},
        "libdwarf": {"libelf"},
        "libelf": set(),
        "mpi": set(),
        "mpileaks": {"callpath", "mpi"},
    } == pkg_cls.possible_dependencies(expand_virtuals=False)


def test_possible_direct_dependencies(mock_packages, mpileaks_possible_deps):
    pkg_cls = spack.repo.path.get_pkg_class("mpileaks")
    deps = pkg_cls.possible_dependencies(transitive=False, expand_virtuals=False)
    assert {
        "callpath": set(),
        "mpi": set(),
        "mpileaks": {"callpath", "mpi"},
    } == deps


def test_possible_dependencies_virtual(mock_packages, mpi_names):
    expected = dict(
        (name, set(spack.repo.path.get_pkg_class(name).dependencies)) for name in mpi_names
    )

    # only one mock MPI has a dependency
    expected["fake"] = set()

    assert expected == spack.package_base.possible_dependencies("mpi", transitive=False)


def test_possible_dependencies_missing(mock_packages):
    pkg_cls = spack.repo.path.get_pkg_class("missing-dependency")
    missing = {}
    pkg_cls.possible_dependencies(transitive=True, missing=missing)
    assert {"this-is-a-missing-dependency"} == missing["missing-dependency"]


def test_possible_dependencies_with_deptypes(mock_packages):
    dtbuild1 = spack.repo.path.get_pkg_class("dtbuild1")

    assert {
        "dtbuild1": {"dtrun2", "dtlink2"},
        "dtlink2": set(),
        "dtrun2": set(),
    } == dtbuild1.possible_dependencies(deptype=("link", "run"))

    assert {
        "dtbuild1": {"dtbuild2", "dtlink2"},
        "dtbuild2": set(),
        "dtlink2": set(),
    } == dtbuild1.possible_dependencies(deptype=("build"))

    assert {
        "dtbuild1": {"dtlink2"},
        "dtlink2": set(),
    } == dtbuild1.possible_dependencies(deptype=("link"))


def test_possible_dependencies_with_multiple_classes(mock_packages, mpileaks_possible_deps):
    pkgs = ["dt-diamond", "mpileaks"]
    expected = mpileaks_possible_deps.copy()
    expected.update(
        {
            "dt-diamond": set(["dt-diamond-left", "dt-diamond-right"]),
            "dt-diamond-left": set(["dt-diamond-bottom"]),
            "dt-diamond-right": set(["dt-diamond-bottom"]),
            "dt-diamond-bottom": set(),
        }
    )

    assert expected == spack.package_base.possible_dependencies(*pkgs)


def setup_install_test(source_paths, install_test_root):
    """
    Set up the install test by creating sources and install test roots.

    The convention used here is to create an empty file if the path name
    ends with an extension otherwise, a directory is created.
    """
    fs.mkdirp(install_test_root)
    for path in source_paths:
        if os.path.splitext(path)[1]:
            fs.touchp(path)
        else:
            fs.mkdirp(path)


@pytest.mark.parametrize(
    "spec,sources,extras,expect",
    [
        (
            "a",
            ["example/a.c"],  # Source(s)
            ["example/a.c"],  # Extra test source
            ["example/a.c"],
        ),  # Test install dir source(s)
        (
            "b",
            ["test/b.cpp", "test/b.hpp", "example/b.txt"],  # Source(s)
            ["test"],  # Extra test source
            ["test/b.cpp", "test/b.hpp"],
        ),  # Test install dir source
        (
            "c",
            ["examples/a.py", "examples/b.py", "examples/c.py", "tests/d.py"],
            ["examples/b.py", "tests"],
            ["examples/b.py", "tests/d.py"],
        ),
    ],
)
def test_cache_extra_sources(install_mockery, spec, sources, extras, expect):
    """Test the package's cache extra test sources helper function."""
    s = spack.spec.Spec(spec).concretized()
    s.package.spec.concretize()
    source_path = s.package.stage.source_path

    srcs = [fs.join_path(source_path, src) for src in sources]
    setup_install_test(srcs, s.package.install_test_root)

    emsg_dir = "Expected {0} to be a directory"
    emsg_file = "Expected {0} to be a file"
    for src in srcs:
        assert os.path.exists(src), "Expected {0} to exist".format(src)
        if os.path.splitext(src)[1]:
            assert os.path.isfile(src), emsg_file.format(src)
        else:
            assert os.path.isdir(src), emsg_dir.format(src)

    s.package.cache_extra_test_sources(extras)

    src_dests = [fs.join_path(s.package.install_test_root, src) for src in sources]
    exp_dests = [fs.join_path(s.package.install_test_root, e) for e in expect]
    poss_dests = set(src_dests) | set(exp_dests)

    msg = "Expected {0} to{1} exist"
    for pd in poss_dests:
        if pd in exp_dests:
            assert os.path.exists(pd), msg.format(pd, "")
            if os.path.splitext(pd)[1]:
                assert os.path.isfile(pd), emsg_file.format(pd)
            else:
                assert os.path.isdir(pd), emsg_dir.format(pd)
        else:
            assert not os.path.exists(pd), msg.format(pd, " not")

    # Perform a little cleanup
    shutil.rmtree(os.path.dirname(source_path))
