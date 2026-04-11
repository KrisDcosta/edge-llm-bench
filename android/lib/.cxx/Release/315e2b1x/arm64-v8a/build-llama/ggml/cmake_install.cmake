# Install script for directory: /Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "0")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/build-llama/ggml/src/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/bin/libggml.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE FILES
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-cpu.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-alloc.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-backend.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-blas.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-cann.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-cpp.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-cuda.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-opt.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-metal.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-rpc.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-virtgpu.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-sycl.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-vulkan.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-webgpu.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/ggml-zendnn.h"
    "/Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/include/gguf.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml-base.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml-base.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml-base.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/bin/libggml-base.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml-base.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml-base.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libggml-base.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/cmake/ggml" TYPE FILE FILES
    "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/build-llama/ggml/ggml-config.cmake"
    "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/build-llama/ggml/ggml-version.cmake"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/arm64-v8a/build-llama/ggml/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
