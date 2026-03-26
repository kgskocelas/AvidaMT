cmake_minimum_required(VERSION 3.14)
project(AvidaMT CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Pull in ealib-modern (defines libea, libea_cmdline, libea_runner targets)
add_subdirectory(../ealib-modern ealib-modern)

# Global compile definitions (mirrors ealib-modern's root CMakeLists.txt)
add_compile_definitions(
    BOOST_BIND_GLOBAL_PLACEHOLDERS
    BOOST_PARAMETER_MAX_ARITY=7
    BOOST_GEOMETRY_EMPTY_INPUT_NO_THROW
)

# AvidaMT's own headers live in include/ and src/
include_directories(include src)

add_executable(avida-logic9          src/logic9.cpp)
add_executable(mt_lr_gls_dol_control src/mt_lr_gls_dol_control.cpp)
add_executable(mt_lr_gls             src/mt_lr_gls.cpp)
add_executable(ts_mt                 src/ts_mt.cpp)

foreach(tgt avida-logic9 mt_lr_gls_dol_control mt_lr_gls ts_mt)
    target_link_libraries(${tgt} PRIVATE libea_runner)
endforeach()
