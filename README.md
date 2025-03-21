# AvidaMT
AvidaMT is the research software built and used for the journal article "Division of Labor Promotes the Entrenchment of Multicellularity" by Peter L. Conlin, Heather J. Goldsby, Eric Libby, Katherine G. Skocelas, William C. Ratcliff, Charles Ofria, and Benjamin Kerr.  Much of the text below is repeated from the methods for this paper.


## Dependencies
* AvidaMT uses the EALib C++ Library for evolutionary algorithms available at https://github.com/dknoester/ealib.git
* EALib requires Boost 1.71.0 and can be challenging to configure on a high performance computing cluster without administrator privileges. We therefore advise against installing AvidaMT directly and instead offer a convenient Singularity Vagrant Box (virtual machine) recipe for it here: https://github.com/peterlconlin/entrenchment


## How It Works
AvidaMT is a command line Linux program for conducting computational evolution experiments examining the conditions that promote the entrenchment of multicellularity and its mechanistic basis. First, the program reads in an extensive, user-defined set of environmental and organismal conditions. Next, it evolves a population of digital organisms under these conditions, recording the organisms’ activity, reproduction, and line of descent. This process is highly resource-intensive and designed to be run on a high-performance computing cluster.

Expanding on the digital evolution software [Avida](https://en.wikipedia.org/wiki/Avida_(software)), AvidaMT’s digital organisms are composed of either a single lower-level unit (which we refer to as a "unicell") or multiple lower-level units (a "multicell"). Each cell's genome is a program consisting of a set of instructions that encode all cell-level behaviors including metabolic activities and self-replication. Cells can acquire new functionality if genomic mutations appropriately modify the underlying instructions. There are nine types of metabolic functions, each corresponding to a binary-logic task (such as calculating the bitwise OR of two values). Any organism with at least one cell performing one of the nine metabolic functions can acquire resources, which are necessary for reproduction.

When a cell replicates within a multicellular organism, it can result in one of two possible outcomes: propagule production or tissue accretion. Propagule production initiates a new organism. It occurs when the daughter of a reproducing cell departs from the parent organism and randomly replaces another organism within the population to grow an offspring. Tissue accretion does this growth. It occurs when the daughter of a reproducing cell remains in the same body (multicell) as its parent cell. Each form of cellular reproduction is specified by distinct instructions in the cell's genome. Unicellular organisms express instructions for propagule production, but not tissue accretion. A transition to multicellularity begins when mutations to a unicellular organism result in the expression of tissue accretion instructions, while retaining propagule production.

An additional distinction between unicells and multicells is the capacity for coordination. Cells within a multicell can use messaging instructions to communicate with their immediate neighbors or coordinate behaviors including terminal differentiation into a "propagule-ineligible" state. Cells in this state can divide via tissue accretion (producing propagule-ineligible daughter cells), but only propagule-eligible cells can initiate new organisms.


## Installing AvidaMT

We suggest using our AvidaMT Singularity Vagrant Box (virtual machine) recipe available here: https://github.com/peterlconlin/entrenchment

However, if you would like to install AvidaMT directly (and deal with the various dependencies that you will also need to install), you can do so via the following steps: 

### Step 1: Install dependencies
Install Boost 1.71.0 and EALib as directed here: https://github.com/dknoester/ealib/blob/master/INSTALL.md

### Step 2: Install AvidaMT
After you've installed Boost & EALib, clone the AvidaMT project into the directory along-side EALib:
```bash
$ git clone https://github.com/heathergoldsby/AvidaMT.git AvidaMT
$ ls
AvidaMT ealib
```

Build AvidaMT:
```bash
$ cd AvidaMT && \
    b2

...found 192 targets...
...updating 10 targets...
clang-darwin.compile.c++ ../ealib/libea/bin/clang-darwin-11.0/debug/link-static/src/expansion.o
clang-darwin.compile.c++ ../ealib/libea/bin/clang-darwin-11.0/debug/link-static/src/main.o
clang-darwin.compile.c++ ../ealib/libea/bin/clang-darwin-11.0/debug/link-static/src/cmdline_interface.o
clang-darwin.archive ../ealib/libea/bin/clang-darwin-11.0/debug/link-static/libea_runner.a
clang-darwin.archive ../ealib/libea/bin/clang-darwin-11.0/debug/link-static/libea_cmdline.a
clang-darwin.compile.c++ bin/clang-darwin-11.0/debug/link-static/src/logic9.o
clang-darwin.link bin/clang-darwin-11.0/debug/link-static/avida-logic9
common.copy /Users/toaster/bin/avida-logic9
...updated 10 targets...

```

And test:
```bash
$ ./bin/clang-darwin-11.0/debug/link-static/avida-logic9 -c etc/logic9.cfg --verbose

Active configuration options:
    config=etc/logic9.cfg
    ea.environment.x=60
    ea.environment.y=60
    ea.mutation.deletion.p=0.05
    ea.mutation.insertion.p=0.05
    ea.mutation.site.p=0.0075
    ea.population.size=3600
    ea.representation.size=100
    ea.run.checkpoint_name=checkpoint.xml
    ea.run.epochs=1
    ea.run.updates=100
    ea.scheduler.resource_slice=30
    ea.scheduler.time_slice=30
    ea.statistics.recording.period=10
    verbose=

update instantaneous_t average_t memory_usage
0 0.0004 0.0004 3.8828
1 0.0000 0.0002 3.8828
2 0.0000 0.0001 3.8828
3 0.0001 0.0001 3.8828
...
97 0.0008 0.0003 4.2695
98 0.0008 0.0003 4.2695
99 0.0007 0.0003 4.2695

```


## Using AvidaMT

(Directions from https://github.com/dknoester/avida4)

* ./mt_lr_gls will run the executable.
* To set the config file, use: ./mt_lr_gls -c config_file_name.cfg. For example, ./mt_lr_gls -c major_transitions.cfg will run the major transitions executable with the setting in the config file.
* To override one value on the command line, do something along the lines of the following: ./mt_lr_gls -c config_file_name.cfg --full.option.name=new_value For example, ./mt_lr_gls -c major_transitions.cfg --ea.gls.and_mutation_mult=6 will set the value of and_mutation_mult to 6, overriding whatever was in the config file.
* To continue an existing run: ./mt_lr_gls -l <path_to_checkpoint_file>/checkpoint-1000000.xml.gz For example, ./mt_lr_gls -l /mnt/home/hjg/mt/033-gls-ramped/a_33/checkpoint-1000000.xml.gz
* To perform further analysis, load the check file and then run an analysis tool. ./mt_lr_gls -l /mnt/home/hjg/mt/033-gls-ramped/a_33/checkpoint-1000000.xml.gz --analyze lod_fitness --ea.analysis.input.filename /mnt/home/hjg/mt/033-gls-ramped/a_33/lod-1000000.xml.gz Note that this example, also loads a line of descent file which can also be analyzed.


## DOI

References to AvidaMT should be pointed to our DOI on Zenodo: https://doi.org/10.5281/zenodo.15066421
