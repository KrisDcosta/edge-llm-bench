# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-src")
  file(MAKE_DIRECTORY "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-src")
endif()
file(MAKE_DIRECTORY
  "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-build"
  "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix"
  "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix/tmp"
  "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix/src/kleidiai_download-populate-stamp"
  "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix/src"
  "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix/src/kleidiai_download-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix/src/kleidiai_download-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/_deps/kleidiai_download-subbuild/kleidiai_download-populate-prefix/src/kleidiai_download-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
