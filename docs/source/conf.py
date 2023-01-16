# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
#

# ================================== Imports ==================================

import os
import re
import sys
import shutil
import inspect
import subprocess
import pkg_resources


# ============================== Build Environment ==============================
# Build behaviour is dependent on environment
on_rtd = os.environ.get('READTHEDOCS') == 'True'

# Configure the path
sys.path.insert(0, os.path.abspath('../../'))
sys.path.append(os.path.abspath('.'))


# Add custom Pygments style if HTML
if 'html' in sys.argv:
    pygments_style = 'tdk_style.TDKStyle'
else:
    pygments_style = 'sphinx'

# on_rtd = True  # Uncomment for testing RTD builds locally


# ============================ Project information ============================

project = 'MyMagento'
copyright = '2023, Adam Korn'
author = 'Adam Korn'

# The full version, including alpha/beta/rc tags
# Simplify things by using the version from setup.py
version = pkg_resources.require("my-magento")[0].version
release = version


# ======================== General configuration ============================

# Doc with root toctree
master_doc = 'contents'  # .rst

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Source File type
source_suffix = '.rst'

# LaTeX settings
latex_elements = {          # Less yucky looking font
    'preamble': r'''
\usepackage[utf8]{inputenc}
\usepackage{charter}
\usepackage[defaultsans]{lato}
\usepackage{inconsolata}
''',
}

# ============================ Extensions ====================================

# Add any Sphinx extension module names here, as strings
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.viewcode',
    'sphinx.ext.linkcode',
    '_ext.linkcode_github'
]


# ====================== Extra Settings for Extensions ========================

# ~~~~ InterSphinx ~~~~
# Add references to Python, Requests docs
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'requests': ('https://requests.readthedocs.io/en/latest/', None),
}

# ~~~~ AutoSectionLabel ~~~~
# Make sure the target is unique
autosectionlabel_prefix_document = True


# ~~~~ Autodoc ~~~~
# Order based on source
autodoc_member_order = 'bysource'
#
# Remove typehints from method signatures and put in description instead
autodoc_typehints = 'description'
#
# Only add typehints for documented parameters (and all return types)
#  ->  Prevents parameters being documented twice for both the class and __init__
autodoc_typehints_description_target = 'documented_params'

# Shorten type hints
python_use_unqualified_type_names = True


# ~~~~~~~~ My Own Thing (replace_autodoc_refs_with_linkcode) ~~~~~~~~~
#
# Directory to save temp .rst file to while docs building
#
rst_build_dir = os.path.abspath('../build/')
#
#
# Source file to convert for GitHub README/PyPi description
#
rst_src = os.path.abspath('README.rst')
#
# File to save the final converted output to
#
rst_out = os.path.abspath('../../README.rst')  # Root of the repository
#
# [Optional] dict of {'ref': 'external_link'} to replace relative links
# like :ref:`ref` with an `ref <external_link>`_ (ex. for PyPi)
#
rst_replace_refs = {
    "interact_with_api": "https://my-magento.readthedocs.io/en/latest/interact-with-api.html#interact-with-api"
}

# The text to use for linkcode source code links
linkcode_link_text = "View on GitHub"

# ============================ HTML Theme Settings ============================

# The theme to use for HTML and HTML Help pages.
html_theme = 'sphinx_rtd_theme'

# Theme Options
# https://sphinx-rtd-theme.readthedocs.io/en/stable/configuring.html#theme-options
#
html_theme_options = {
    # Add the [+] signs to nav
    'collapse_navigation': False,
    # Prev/Next buttons also placed at the top bc it'd be cruel not to
    'prev_next_buttons_location': 'both',
}

html_context = {
    'display_github': True,
    'github_user': 'TDKorn',
    'github_repo': 'my-magento',
    'github_version': None
}

# ============================ Linkcode Extension Settings ============================
#
#                     Adapted from https://github.com/nlgranger/SeqTools
#
#

# Get the blob to link to on GitHub
linkcode_revision = "master"

try:
    # lock to commit number
    cmd = "git log -n1 --pretty=%H"
    head = subprocess.check_output(cmd.split()).strip().decode('utf-8')
    linkcode_revision = head

    # if we are on master's HEAD, use master as reference
    cmd = "git log --first-parent master -n1 --pretty=%H"
    master = subprocess.check_output(cmd.split()).strip().decode('utf-8')
    if head == master:
        linkcode_revision = "master"

    # if we have a tag, use tag as reference
    cmd = "git describe --exact-match --tags " + head
    tag = subprocess.check_output(cmd.split(" ")).strip().decode('utf-8')
    linkcode_revision = tag

except subprocess.CalledProcessError:
    pass

# Set GitHub version to be same as linkcode
html_context['github_version'] = linkcode_revision

# Source URL template; formatted + returned by linkcode_resolve
linkcode_url = "https://github.com/tdkorn/my-magento/blob/" \
               + linkcode_revision + "/{filepath}#L{linestart}-L{linestop}"

# Hardcoded Top Level Module Path since MyMagento isn't PyPi release name
modpath = pkg_resources.require('my-magento')[0].location


def linkcode_resolve(domain, info):
    """Returns a link to the source code on GitHub, with appropriate lines highlighted

    Adapted from https://github.com/nlgranger
    """
    if domain != 'py' or not info['module']:
        return None

    modname = info['module']
    fullname = info['fullname']

    submod = sys.modules.get(modname)
    if submod is None:
        print(f'No submodule found for {fullname}')
        return None

    obj = submod
    for part in fullname.split('.'):
        try:
            obj = getattr(obj, part)
            print(obj)
        except Exception:
            print(f'error getting part? obj = {obj}, part = {part})')
            return None

    try:
        filepath = os.path.relpath(inspect.getsourcefile(obj), modpath)
        if filepath is None:
            print(f'No filepath found for {obj} in module {modpath}...?')
            return
    except Exception as e:
        return print(  # ie. None
            f'Exception raised while trying to retrieve module path for {obj}:',
            e, sep='\n'
        )

    try:
        source, lineno = inspect.getsourcelines(obj)
    except OSError:
        print(f'failed to get source lines for {obj}')
        return None
    else:
        linestart, linestop = lineno, lineno + len(source) - 1

    # Format link using the filepath of the source file plus the line numbers
    # Fix links with "../../../" or "..\\..\\..\\"
    filepath = '/'.join(filepath.lstrip('..\\/checkouts/latest').split('\\'))

    # Example of final link: # https://github.com/tdkorn/my-magento/blob/sphinx-docs/magento/utils.py#L355-L357
    final_link = linkcode_url.format(
        filepath=filepath,
        linestart=linestart,
        linestop=linestop
    )
    print(f"Final Link for {fullname}: {final_link}")

    # Use the link to replace directives with links in the README for GitHub/PyPi
    if not on_rtd:
        replace_autodoc_refs_with_linkcode(
            info=info,
            link=final_link,
            rst_src=rst_src,
        )

    return final_link


def replace_autodoc_refs_with_linkcode(info: dict, link: str, rst_src: str):
    """Replaces Sphinx autodoc cross-references in a .rst file with linkcode links to highlighted GitHub source code

    Essentially turns your GitHub README into Sphinx-like documentation contained fully within the repository


    =================================  By https://github.com/TDKorn  =====================================


    For example, :meth:`~.InstaClient.get_user` would be rendered in HTML as an outlined "get_user()" link
    that contains an internal reference to the corresponding documentation entry (assuming it exists)

    We love it, it's great. Fr. But it's ugly and useless on GitHub and PyPi. Literally so gross.

    This function replaces cross-references in the ``rst_src`` file with the links generated by linkcode,
    which take you to the source file and highlight the full definition of the class/method/function/target

    .. note:: links are of the format https://github.com/user/repo/blob/branch/package/file.py#L30-L35

        For example,
        `get_user() <https://github.com/TDKorn/insta-tweet/blob/master/InstaTweet/instaclient.py#L48-L71>`_


    :param info: the info dict from linkcode_resolve
    :param link: link to the highlighted GitHub source code, generated by linkcode
    :param rst_src: the .rst file to use as the initial source of content
    """
    if not rst_src.endswith('.rst'):
        raise TypeError

    # On the first function call that actually replaces a cross-reference with a link,
    # the content from ``rst_src`` is copied and saved to a temporary rst file in ``rst_build_dir``
    #
    # All function calls afterwards will use this temp file as the source and output file
    # When the build completes, it will be moved to the specified ``rst_out`` location
    #
    rst_temp = os.path.join(rst_build_dir, os.path.basename(rst_src))

    # If the temp output file already exists, use it as the source, since
    # the content from ``rst_src`` is already copied to it (and possibly edited)
    if os.path.exists(rst_temp):
        rst_src = rst_temp

    else:
        # If not, it's the first function call. It needs to be created
        rst_src = os.path.abspath(rst_src)

        # And if the rst build directory doesn't exist, create it too
        if not os.path.exists(rst_build_dir):
            os.mkdir(rst_build_dir)

    # Read in the rst
    rst = read(rst_src)

    # Use the linkcode data that was provided to see what the reference target is
    # Ex:  Class.[method] // module.[function] // [function]
    ref_name = info['fullname'].split('.')[-1]

    # The rst could have :meth:`~.method` or :meth:`~.Class.method` or :class:`~.Class` or...
    # Regardless, there's :directive:`[~][module|class][.]target` where [] is optional
    pattern = rf":\w+:`~?\.?\w?\.{ref_name}`"

    # See if there's any reference in the rst, and figure out what it is
    if match := re.findall(pattern, rst):
        directive = match[0].split(':')[1]
    else:
        print('No references found for', ref_name)
        return None

    # Format the name of methods
    if directive == 'meth':
        ref_name += "()"

    # Format the link -> `method() <https://www.github.com/.../file.py#L10-L19`_
    rst_link = f"`{ref_name} <{link}>`_"

    # Then take the link and sub that hoe in!!
    subbed_rst = re.sub(pattern, rst_link, rst)

    # Save to the temp build rst file
    with open(rst_temp, 'w', encoding='utf-8') as f:
        f.write(subbed_rst)

    print(f'Added reST links for {ref_name}: {rst_link}')
    return {'info': info, 'rst_link': rst_link}


# ---- Methods for "build-finished" Core Event ----------------------

def read(file):
    with open(file, 'r', encoding='utf-8') as f:
        return u'{}'.format(f.read())


def replace_rst_refs(rst: str, refs: dict) -> str:
    """Post-processes the generated rst, replacing :ref: with external links (ex. for PyPi)

    :param rst: the text of the .rst file
    :param refs: dict of {'reference': 'external_link'}
    :return: the processed rst text
    """
    for ref, external_link in refs.items():
        rst = re.sub(
            pattern=rf":ref:`{ref}`",
            repl=f"`{ref} <{external_link}>`_",
            string=rst
        )
    return rst


def replace_rst_images(rst: str) -> str:
    """Post-processes the generated rst, replacing relative image paths with external RTD links

    Probably temporary until I write a proper function that adjusts the paths when moving to ``rst_out``

    :param rst: the text of the .rst file
    :return: the processed rst text
    """
    return re.sub(
        # .. image:: {..}/_static/(filename.ext)
        pattern=r".. image:: \S+_static/(\w+\.\w{3,4})",
        repl=r".. image:: https://instatweet.readthedocs.io/en/latest/_images/\1",
        string=rst
    )


def move_generated_rst_file(app, exception):
    """Moves the generated rst file from ``rst_temp`` to ``rst_out``"""
    built_rst = os.path.join(
        rst_build_dir, os.path.basename(rst_src)
    )
    if os.path.exists(built_rst):
        rst = replace_rst_images(
            rst=read(built_rst)
        )
        if rst_replace_refs:
            rst = replace_rst_refs(
                rst, refs=rst_replace_refs
            )
        with open(rst_out, 'w', encoding='utf-8') as f:
            f.write(rst)

        return print(
            f'Moved generated .rst file from {built_rst} to {rst_out}'
        )
    if exception:
        return print(
            "Build .rst file not found in build dir, exception raised:",
            exception, sep='\n'
        )
    return print('.rst file not generated, no exception was raised')
# ---- Skip and Setup Method -------------------------------------------------

def skip(app, what, name, obj, would_skip, options):
    """Include __init__ as a documented method"""
    if name in ('__init__',):
        return False
    return would_skip


def setup(app):
    app.connect('autodoc-skip-member', skip)
    app.connect('build-finished', move_generated_rst_file)
    app.add_css_file("custom.css")
