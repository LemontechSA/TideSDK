#!/usr/bin/env python

# This file has been modified from its orginal sources.
#
# Copyright (c) 2012 Software in the Public Interest Inc (SPI)
# Copyright (c) 2012 David Pratt
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright (c) 2008-2012 Appcelerator Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import SCons.Variables
import SCons.Environment
from SCons.Script import *
import os
import glob
import re
import utils
import types
import os.path as path
import effess

class Module(object):
    def __init__(self, name, version, dir):
        self.name = name
        self.version = version
        self.dir = dir

    def __str__(self):
        return self.dir

class BuildConfig(object):
    def __init__(self, **kwargs):
        self.debug = False
        self.os = None
        self.modules = []
        self.tidelite = False
        if not hasattr(os, 'uname') or self.matches('CYGWIN'):
            self.os = 'win32'
            self.arch = 'x86'
            os.environ['PROCESSOR_ARCHITECTURE'] = 'x86'

        elif self.matches('Darwin'):
            self.os = 'osx'
            self.arch = 'x86'

        elif self.matches('Linux'):
            self.os = 'linux'
            if (os.uname()[4] == 'x86_64'):
                self.arch = os.uname()[4]
            else:
                self.arch = 'x86'

        vars = SCons.Variables.Variables(args = ARGUMENTS)
        vars.Add('PRODUCT_VERSION', 'The product version for Tide', kwargs['PRODUCT_VERSION'])
        vars.Add('PRODUCT_NAME', 'The product name that libTide will display (default: "Tide")', kwargs['PRODUCT_NAME'])
        vars.Add('GLOBAL_NAMESPACE','The name of the Tide global variable', kwargs['GLOBAL_NAMESPACE'])
        vars.Add('CONFIG_FILENAME','The name of the Tide config file', kwargs['CONFIG_FILENAME'])
        vars.Add('DISTRIBUTION_URL','The base URL of all streams', kwargs['DISTRIBUTION_URL'])
        vars.Add('MSVC_VERSION', '', '8.0Exp')

        def add_environ_arg(key, description, default):
            default_value = default
            if key in os.environ:
                default_value = os.environ[key]
            vars.Add(key, description, default_value)

        #add_environ_arg('MSPSDK', 'Path of the Microsoft Platform SDK', 'C:\\Program Files\\Microsoft Platform SDK for Windows Server 2003 R2')
        add_environ_arg('MSPSDK', 'Path of the Microsoft Platform SDK', 'C:\\Program Files\\Microsoft Platform SDK')
        add_environ_arg('MSVS', 'Path of Microsoft Visual Studio', 'C:\\Program Files\\Microsoft Visual Studio 8')
        add_environ_arg('PKG_CONFIG_PATH', 'The path for pkg-config', '/usr/lib/pkgconfig')
        add_environ_arg('PYTHON_VERSION', 'The version of Python to build against', '2.7')
        add_environ_arg('PYTHON_INCLUDE', 'The Python include directory', '/usr/include/python2.7')

        self.env = SCons.Environment.Environment(variables = vars)
        self.utils = utils.BuildUtils(self)
        self.env.Append(CPPDEFINES = [
            ['OS_' + self.os.upper(), 1],
            ['_OS_NAME', self.os],
            ['_PRODUCT_VERSION', '${PRODUCT_VERSION}'],
            ['_PRODUCT_NAME', '${PRODUCT_NAME}'],
            ['_GLOBAL_NAMESPACE', '${GLOBAL_NAMESPACE}'],
            ['_CONFIG_FILENAME' , '${CONFIG_FILENAME}'],
            ['_BOOT_RUNTIME_FLAG', '${BOOT_RUNTIME_FLAG}'],
            ['_BOOT_HOME_FLAG', '${BOOT_HOME_FLAG}'],
            ['_DISTRIBUTION_URL', '${DISTRIBUTION_URL}'],
        ])
        self.version = self.env['PRODUCT_VERSION']

        self.dir = path.abspath(path.join(kwargs['BUILD_DIR'], self.os))
        self.dist_dir = path.join(self.dir, 'dist')
        self.runtime_build_dir = path.join(self.dir, 'runtime')
        self.runtime_template_dir = path.join(self.runtime_build_dir, 'template')

        self.env.Append(LIBPATH=[self.dir])

        if ARGUMENTS.get('lite'):
            self.tidelite = True
            self.env.Append(CPPDEFINES='TIDE_LITE')

        self.init_os_arch()
        self.build_targets = []  # targets needed before packaging & distribution can occur
        self.staging_targets = []  # staging the module and sdk directories
        self.dist_targets = [] # targets that *are* packaging & distribution
        Alias('build', [])
        Alias('stage', [])
        Alias('dist', [])

        # SCons can't read the Visual Studio settings yet so we
        # have to force it to use the Platform SDK directories
        if self.is_win32():
            self.env.Prepend(PATH=['${MSPSDK}'])
            self.env.Prepend(CPPPATH=['${MSPSDK}\\include'])
            self.env.Prepend(LIBPATH=['${MSPSDK}\\lib'])
            self.env.Prepend(CPPPATH=['${MSVS}\\VC\\atlmfc\\include'])

    def set_tide_source_dir(self, dir):
        self.tide_source_dir = path.abspath(dir)
        self.tide_include_dir = path.join(self.dir, 'sdk', 'include')
        self.tide_utils_dir = path.join(self.tide_source_dir, 'lib', 'utils');

    def init_os_arch(self):
        if self.is_linux() and self.is_64():
            self.env.Append(CPPFLAGS=['-m64', '-Wall', '-Werror','-fno-common', '-fvisibility=hidden', '-fno-strict-aliasing'])
            self.env.Append(LINKFLAGS=['-m64'])
            self.env.Append(CPPDEFINES = ('OS_64', 1))
        elif self.is_linux() or self.is_osx():
            self.env.Append(CPPFLAGS=['-m32', '-Wall', '-fno-common', '-fvisibility=hidden', '-fno-strict-aliasing'])
            self.env.Append(LINKFLAGS=['-m32'])
            self.env.Append(CPPDEFINES = ('OS_32', 1))
        else:
            self.env.Append(CPPDEFINES = ('OS_32', 1))

        if self.is_osx():
            sdk_version = '10.8'
            xcode_path = os.popen("/usr/bin/xcode-select --print-path").readline().rstrip('\n')
            if(False == os.path.exists(xcode_path)):
                print 'XCode not found. Make sure you have set your xcode with xcode-select'
                Exit(2)
            sdk_dir = '%s/Platforms/MacOSX.platform/Developer/SDKs/MacOSX%s.sdk' % (xcode_path, sdk_version)
            sdk_minversion = '-mmacosx-version-min=%s' % sdk_version
            self.env['MACOSX_DEPLOYMENT_TARGET'] = '%s' % sdk_version

            self.env['CC'] = ['gcc', '-arch', 'i386']
            self.env['CXX'] = ['g++', '-arch', 'i386']
            self.env.Append(FRAMEWORKS=['Foundation', 'IOKit'])
            self.env.Append(CXXFLAGS=['-isysroot', sdk_dir, sdk_minversion, '-x', 'objective-c++'])
            self.env.Append(LINKFLAGS=['-isysroot', sdk_dir, '-syslibroot,' + sdk_dir, '-lstdc++', sdk_minversion])
            self.env.Append(CPPFLAGS=[
                '-Wall', '-fno-common', '-fvisibility=hidden',
                '-DMACOSX_DEPLOYMENT_TARGET=' + self.env['MACOSX_DEPLOYMENT_TARGET']])

    def matches(self, n): return os.uname()[0].find(n) != -1
    def is_linux(self): return self.os == 'linux'
    def is_osx(self): return self.os == 'osx'
    def is_win32(self): return self.os == 'win32'
    def is_64(self): return self.arch == 'x86_64'
    def is_32(self): return not self.is_64()

    def get_module(self, name):
        for module in self.modules:
            if module.name == name:
                return module
        return None

    def add_thirdparty(self, env, name):
        cpppath = libpath = libs = None
        if name is 'poco':
            cpppath = [self.tp('poco', 'include')]
            libpath = [self.tp('poco', 'lib')]
            libs = ['PocoFoundation', 'PocoNet', 'PocoUtil', 'PocoXML',
                'PocoZip', 'PocoData', 'PocoSQLite']

        if name is 'curl':
            cpppath = [self.tp('curl', 'include')]
            libpath = [self.tp('curl', 'lib')]
	    if self.is_win32():
	        libs = ['libcurl_imp']
            else:
                libs = ['curl']

        elif name is 'libxml':
            if self.is_osx():
                cpppath = ['/usr/include/libxml2']
                libs = ['xml2']
            elif self.is_win32():
                cpppath = [self.tp('libxml', 'include'), self.tp('icu', 'include')]
                libs = ['libxml2']

        elif name is 'cairo' and self.is_win32():
            cpppath = [self.tp('cairo', 'include')]
            libpath = [self.tp('cairo', 'lib')]
            libs = ['cairo']

        elif name is 'libproxy' and (self.is_win32() or self.is_linux()):
            cpppath = [self.tp('libproxy', 'include')]
            libpath = [self.tp('libproxy', 'lib')]
            libs = ['libproxy']

        elif name is 'libsoup' and self.is_linux():
            cpppath = [self.tp('libsoup', 'include')]
            libpath = [self.tp('libsoup', 'lib')]
            libs = ['libsoup-2.4', 'libsoup-gnome-2.4']

        elif name is 'boost':
            if not self.is_linux():
                cpppath = [self.tp('boost', 'include')]
                libpath = [self.tp('boost', 'lib')]
            # add mac libs as it doesn't pick them up automatically
            if self.is_osx() or self.is_linux():
                libs = ['boost_system-mt', 'boost_thread-mt']

        elif name is 'boost_include':
            if not self.is_linux():
                cpppath = [self.tp('boost', 'include')]

        elif name is 'openssl':
            cpppath = [self.tp('openssl', 'include')]
            libpath = [self.tp('openssl', 'lib')]
            if self.is_win32():
                libs = ['libeay32', 'ssleay32']
            if self.is_osx():
                libs = ['ssl', 'crypto']

        if name is 'webkit':
            if self.is_win32():
                cpppath = [self.tp('webkit', 'include')]
                libpath = [self.tp('webkit', 'lib')]
	        if self.tidelite is False:
                    cpppath = [self.tp('webkit-patch', 'include')]
                    libpath = [self.tp('webkit-patch', 'lib')]
	        else:
                    cpppath = [self.tp('webkit-lite', 'include')]
                    libpath = [self.tp('webkit-lite', 'lib')]

            if self.is_linux():
                if self.tidelite is False:
                    cpppath = [self.tp('webkit', 'include')]
                    libpath = [self.tp('webkit', 'lib')]
                    cpppath.append(self.tp('webkit', 'include', 'glib-2.0'))
                else:
                    cpppath = ['/usr/include/webkitgtk-1.0/']

            if self.is_win32():
                suffix = ''
                if ARGUMENTS.get('webkit_debug', None):
                    suffix = '_debug'
                libs = ['WebKit', 'WebKitGUID', 'JavaScriptCore']
                libs = [x + suffix for x in libs]

            if self.is_linux():
                if self.tidelite is False:
                    libs = ['webkittitanium-1.0']
                else:
                    libs = ['webkitgtk-1.0']

            if self.is_osx():
                if self.tidelite is False:
                    env.Append(FRAMEWORKPATH=[self.tp('webkit')])
                env.Append(FRAMEWORKS=['WebKit', 'JavaScriptCore'])

        if cpppath: env.Append(CPPPATH=cpppath)
        if libpath: env.Append(LIBPATH=libpath)
        if libs: env.Append(LIBS=[libs])

    def tp(self, *parts):
        full_path = self.third_party
        for part in parts:
            full_path = path.join(full_path, part)
        return full_path

    def cwd(self, depth=1):
        return path.dirname(sys._getframe(depth).f_code.co_filename)

    def unpack_targets(self, t, f):
        if not t: return
        if type(t) == types.ListType:
            for x in t: self.unpack_targets(x, f)
        else:
            f(t)

    def mark_build_target(self, t):
        self.unpack_targets(t, self.mark_build_target_impl)
    def mark_build_target_impl(self, t):
        Default(t)
        self.build_targets.append(t)
        Alias('build', self.build_targets)

    def mark_stage_target(self, t):
        self.unpack_targets(t, self.mark_stage_target_impl)
    def mark_stage_target_impl(self, t):
        self.staging_targets.append(t)
        Depends(t, 'build')
        Alias('stage', self.staging_targets)

    def mark_dist_target(self, t):
        self.unpack_targets(t, self.mark_dist_target_impl)
    def mark_dist_target_impl(self, t):
        self.dist_targets.append(t)
        Depends(t, 'stage')
        Alias('dist', self.dist_targets)

