# Install script for directory: /Users/krisdcosta/291_EAI/vendor/llama.cpp/ggml/src

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
  include("/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/build-llama/ggml/src/ggml-cpu/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-x64.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-x64.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-x64.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-x64.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-x64.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-x64.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-x64.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sse42.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sse42.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sse42.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-sse42.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sse42.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sse42.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sse42.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sandybridge.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sandybridge.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sandybridge.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-sandybridge.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sandybridge.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sandybridge.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sandybridge.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-ivybridge.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-ivybridge.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-ivybridge.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-ivybridge.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-ivybridge.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-ivybridge.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-ivybridge.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-piledriver.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-piledriver.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-piledriver.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-piledriver.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-piledriver.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-piledriver.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-piledriver.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-haswell.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-haswell.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-haswell.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-haswell.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-haswell.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-haswell.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-haswell.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-skylakex.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-skylakex.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-skylakex.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-skylakex.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-skylakex.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-skylakex.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-skylakex.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cannonlake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cannonlake.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cannonlake.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-cannonlake.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cannonlake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cannonlake.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cannonlake.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cascadelake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cascadelake.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cascadelake.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-cascadelake.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cascadelake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cascadelake.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cascadelake.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-icelake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-icelake.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-icelake.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-icelake.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-icelake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-icelake.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-icelake.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cooperlake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cooperlake.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cooperlake.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-cooperlake.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cooperlake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cooperlake.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-cooperlake.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-zen4.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-zen4.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-zen4.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-zen4.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-zen4.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-zen4.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-zen4.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-alderlake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-alderlake.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-alderlake.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-alderlake.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-alderlake.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-alderlake.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-alderlake.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sapphirerapids.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sapphirerapids.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sapphirerapids.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE MODULE FILES "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/bin/libggml-cpu-sapphirerapids.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sapphirerapids.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sapphirerapids.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/Users/krisdcosta/Library/Android/sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/libggml-cpu-sapphirerapids.so")
    endif()
  endif()
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/krisdcosta/291_EAI/android/lib/.cxx/Release/315e2b1x/x86_64/build-llama/ggml/src/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
