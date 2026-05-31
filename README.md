[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![MIT][license-shield]][license-url]

<!-- PROJECT LOGO -->
<div align="center">

<h3 align="center">STT-HE</h3>

  <p align="center">
    Speech To Text Synthesis From Hebrew -> Hebrew
  </p>

</div>

<!-- ABOUT THE PROJECT -->
## About The Project

This is a **(WIP)** Low-Latency Speech-To-Text Server in C++, using  
already available Machine Learning Solutions such as [whisper.cpp](https://github.com/ggml-org/whisper.cpp)**/**[faster-whisper](https://github.com/SYSTRAN/faster-whisper) with their [CTranslate2](https://github.com/OpenNMT/CTranslate2) Engine  

The Goal of this project is to enable Hebrew->Hebrew Translation, making EVERYTHING as fast as feasibly possible for local/Embedded use

<br></br>

### Project Structure

The project has the same structure as my other project [tree](https://github.com/inonitz/tree), except...  

* Sandbox Mostly contains code for Work In Progress, mainly python code for benchmarking/testing new ideas
* `sttserv/` is the server library/executable  

<br></br>


<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* CMake
* Working compiler toolchain, preferably clang  
  Windows: You should use [llvm](https://github.com/llvm/llvm-project/releases)  
  Linux:  
    1. [installing-specific-llvm-version](https://askubuntu.com/questions/1508260/how-do-i-install-clang-18-on-ubuntu)
    2. [configuring-symlinks](https://unix.stackexchange.com/questions/596226/how-to-change-clang-10-llvm-10-etc-to-clang-llvm-etc)
    3. **You Don't have to use LLVM, gcc works too**

* Python 3 installed
* ~6GiB of storage *(At Most!)* for the repository + local LLM's

### Building & (Maybe) Running

For Running/Using the python Sandbox:  

```sh
git clone https://github.com/inonitz/sttserv --branch dev desired_folder_path_from_cwd
cd desired_folder_path_from_cwd/sttserv
cd sandbox
./venv.sh # Setup Python Virtual Environment (Linux Shell)
.\venv.ps1 # Setup Python Virtual Environment (Windows powershell)
```

For Building the Server itself:

```sh
git clone --recurse-submodules https://github.com/inonitz/sttserv --branch dev desired_folder_path_from_cwd
cd desired_folder_path_from_cwd/sttserv
```

<br></br>

## Everything Beyond This Point is currently Old & Irrelevant, will be updated in due time! :)

#### Configuring The Server

#### ***This Part Is From an old project but may still be useful when rewriting***

Because This project is somewhat big and building manually is cumbersome,  
I Wrote build scripts [build.sh](https://github.com/inonitz/tree/build.sh), [build.ps1](https://github.com/inonitz/tree/build.ps1) for Linux & Windows Respectively  

**By Default, The project will try to build EVERYTHING** - If you do not want that,  
add the following flags to your cmake invocation (Or If Building with the scripts, disable in your platforms' Script):

* Project Specific:
  * ``` -DENABLE_SANITIZER_ADDRESS=OFF ```
  * ``` -DENABLE_SANITIZER_UNDEFINED=OFF ```
  * ``` -DENABLE_SANITIZER_MEMORY=OFF ```
  * ``` -DENABLE_LINK_TIME_OPTIMIZATION=OFF ```
  * ``` -DTREELIB_BUILD_TESTS=OFF ```

* Dependencies:
  * ``` -DCMAKE_C_COMPILER=clang ```
  * ``` -DCMAKE_CXX_COMPILER=clang++ ```
  * ``` -DCMAKE_EXPORT_COMPILE_COMMANDS=1 ```
  * ``` -DCMAKE_COLOR_DIAGNOSTICS=ON ```
  * ``` -DBUILD_GMOCK=OFF ```
  * ``` -DINSTALL_GTEST=OFF ```
  * ``` -DBENCHMARK_ENABLE_INSTALL=OFF ```
  * ``` -DBENCHMARK_INSTALL_DOCS=OFF ```
  * ``` -DBENCHMARK_INSTALL_TOOLS=OFF ```
  * ``` -DBENCHMARK_DOWNLOAD_DEPENDENCIES=OFF ```
  * ``` -DBENCHMARK_ENABLE_TESTING=OFF ```
  * ``` -DBENCHMARK_ENABLE_GTEST_TESTS=OFF ```
  * ``` -DBENCHMARK_USE_BUNDLED_GTEST=OFF ```

Windows:

```sh
.\build.ps1 -Help
.\build.ps1 -BuildType release -LinkType shared -Action configure
.\build.ps1 -BuildType release -LinkType shared -Action build
.\build.ps1 -BuildType release -LinkType shared -Action test/benchmark
```

Linux:

```sh
./build.sh --help
./build.sh release static configure
./build.sh release static build
./build.sh release static test/benchmark
```

<br></br>

<!-- USAGE EXAMPLES -->
## Usage

### In Source Build

In your CMakeLists.txt:

```sh
add_subdirectory(your_directory/tree)
```

Also, Don't forget to link to the library:

```sh
target_link_libraries(your_target_executable/library PRIVATE TREELIB::treelib)
```

### Out-Of-Source (Submodule/etc...) Build

```sh
git submodule add https://github.com/inonitz/tree your_dependency_folder/tree
git submodule init
git submodule update
```

In your CMakeLists.txt:

```sh
add_subdirectory(your_dependency_folder/tree)
```

Also, Don't forget to link to the library:

```sh
target_link_libraries(your_target_executable/library PRIVATE TREELIB::treelib)
```

<br></br>

## Roadmap/TODO

* Optimize binaryTree::AVLDeleteIterative in AVLTreeGeneric.tpp, similarly to AVLInsertIterative in AVLTree.c
* Add Automatic Testing Matrix For architecture/OS/Build Type (Shared/Dynamic/Static, Debug/Release, ...)  
  * **(involves CI/CD Pipelines which I'm not very familiar with/not interested in currently)**

<br></br>

<!-- CONTRIBUTING -->
## Contributing

If you have a suggestion, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".  

<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE` file for more information.

<br></br>

<!-- Benchmarks -->
## Benchmarks

### *A few notes before the graphs*

**The following benchmarks were tested on my i7-8750H Laptop with 16GBx2 2666Mhz DDR4 Ram**  

* Search, Deletion & Insertion were Tested on 6 Different Data Structures  
  1. std::set (clang-18)  
  2. std::unordered_map (clang-18)  
  3. C Implementation of an AVL Tree  
  4. C++ Implementation Of an Iterative AVL Tree  
  5. C++ Implementation Of a Recursive AVL Tree  
  6. C++ Implementation Of a 'Flat' Iterative AVL Tree, specifically:  
      * Specialized Freelist Node-Allocator
      * Reusing of freed nodes using a local Stack
      * Metadata packing to 8 bytes, enabling a maximum of ~258 Million Elements  
        This was done to reduce memory footprint, memory chasing & improve  
        cache utilization
  
* Each Data Structure was specialized to 3 Base Types
  1. u64 (trivial plain old data type)
  2. DummyRecord (Multiple Cache-Lines in Size, but still POD)
  3. std::string (Non-Trivial Type with complex construction, copying and destruction)

* Benchmarking was done concurrently to save time ([Approx ~5 Hours Serially](https://github.com/inonitz/tree/blob/master/scripts/iterations/3/test_benchmark_session_linux.txt))

<!-- <img src="https://github.com/inonitz/tree/blob/master/scripts/iterations/3/plots/.svg"> -->

### **Finally, the benchmarks!**

#### Searching for a Node

<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_u64_Search.svg">
<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_DummyRecord_Search.svg">
<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_std_string_Search.svg">

#### Inserting Nodes

<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_u64_Insertion.svg">
<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_DummyRecord_Insertion.svg">
<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_std_string_Insertion.svg">

#### Deleting Nodes

<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_u64_Deletion.svg">
<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_DummyRecord_Deletion.svg">
<img src="https://raw.githubusercontent.com/inonitz/tree/master/scripts/iterations/3/plots/plot_std_string_Deletion.svg">

## Conclusions/Lessons Learned

* Recursion is pretty good for small *N*, but gets out of hand pretty quickly
* Looking at the benchmarks, I can confidently assume that FlatAVLTree had way better cache utilization,  
  due to the spatial locality of the internal nodes being placed in a big buffer,  
  as compared with the usual implementation requiring pointer chasing and using malloc/free/new/delete
* Premature Optimization is *still* the root of all evil, but indeed a very convenient learning tool
* Never assume **anything** until you benchmark it
* The Standard Library folks **really do know what they're doing**
* If you think a task will require an allocated Time *N*, it will probably take *2N*, if not more
* Testing is required to ensure growing complexity in a system/project doesn't completely overwhelm and impede the rate of development,  
  more formally known as [Lehmans' Law of Software Evolution](https://en.wikipedia.org/wiki/Lehman%27s_laws_of_software_evolution)  (literally just found this out now lol)

<!-- ACKNOWLEDGEMENTS -->
## Acknowledgements

* [GoogleBenchmark](https://github.com/google/benchmark)
* [GoogleTest](https://google.github.io/googletest)
* [CMocka](https://cmocka.org)
* [CMake](https://cmake.org/cmake/help/latest/guide/tutorial/index.html)
* [Intrusive AVL Tree by Eric Biggers](https://github.com/ebiggers/avl_tree)

<!-- References -->
## References

* [Modern CMake](https://cliutils.gitlab.io/modern-cmake/README.html)
* [Best-README](https://github.com/othneildrew/Best-README-Template)
* [AVL Tree Playlist by William Fiset](https://youtube.com/playlist?list=PLDV1Zeh2NRsD06x59fxczdWLhDDszUHKt&si=N7kZmzkVAIHU4jjc)
* [Jenny's Data Structures & Algorithm Course](https://youtube.com/playlist?list=PLdo5W4Nhv31bbKJzrsKfMpo_grxuLl8LU&si=UGaS5lt1SiFYFAN-)  
  * In particular, her videos regarding AVL Tree Rotations
* [W3Schools AVL Trees](https://www.w3schools.com/dsa/dsa_data_avltrees.php)
* [Typed Tests (GoogleTest)](https://google.github.io/googletest/advanced.html#typed-tests)
* [GoogleBenchmark User Guide](https://github.com/google/benchmark/blob/main/docs/user_guide.md)
  * I found the following references most relevant:
  * [Setup & Teardown](https://github.com/google/benchmark/blob/main/docs/user_guide.md#setupteardown)
  * [Templates](https://github.com/google/benchmark/blob/main/docs/user_guide.md#templated-benchmarks)
  * [Fixtures](https://github.com/google/benchmark/blob/main/docs/user_guide.md#Fixtures)
  * [Custom Counters](https://github.com/google/benchmark/blob/main/docs/user_guide.md#custom-counters)
  * [PauseTiming() & ResumeTiming()](https://github.com/google/benchmark/blob/main/docs/user_guide.md#controlling-timers)
* [Tick Formatting in Matplotlib](https://matplotlib.org/stable/gallery/ticks/tick-formatters.html)
* [Axis Ticks in Matplotlib](https://matplotlib.org/stable/users/explain/axes/axes_ticks.html)
* [Pathlib Basic Usage](https://stackoverflow.com/a/35188296)

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/inonitz/tree?style=for-the-badge&color=blue
[contributors-url]: https://github.com/inonitz/tree/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/inonitz/tree?style=for-the-badge&color=blue
[forks-url]: https://github.com/inonitz/tree/network/members
[stars-shield]: https://img.shields.io/github/stars/inonitz/tree?style=for-the-badge&color=blue
[stars-url]: https://github.com/inonitz/tree/stargazers
[license-shield]: https://img.shields.io/github/license/inonitz/tree?style=for-the-badge
[license-url]: https://github.com/inonitz/tree/blob/main/LICENSE

<!-- [CMake-url]: https://cmake.org/cmake/help/latest/guide/tutorial/index.html
[CMake.js]: https://gitlab.kitware.com/uploads/-/system/project/avatar/541/cmakelogo-centered.png?width=128

[CMocka-url]: https://cmocka.org
[CMocka.js]: https://avatars.githubusercontent.com/u/5657447?s=128&v=0

[GoogleTest-url]: https://google.github.io/googletest
[GoogleTest.js]: https://avatars.githubusercontent.com/u/1342004?s=128&v=4

[GoogleBench-url]: https://github.com/google/benchmark
[GoogleBench.js]: https://avatars.githubusercontent.com/u/1342004?s=128&v=4 -->
