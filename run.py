#!/usr/bin/env python3

import os
import subprocess
import argparse
import sys

#sys.path.append(r"/home/hhe07/Documents/openrisc/litex/")

import sim

import re

import shutil
import glob
import json

from git import Repo

from Embench import build_all
from Embench import benchmark_speed


def collect_cpu_and_toolchain_data(cpu_report, mode, test_path):
    working_dir = os.getcwd()
    d = {}

    if os.path.exists(f'pythondata-cpu-{cpu_report["CPU"]}'):
        os.chdir(f'pythondata-cpu-{cpu_report["CPU"]}')
        repo = Repo(os.getcwd())
        d['CPU'] = {
            cpu_report['CPU']: repo.head.commit.hexsha
        }
        os.chdir(working_dir)

    software_used = {
        'toolchain': f'{cpu_report["TRIPLE"]}-gcc',
        'verilator': 'verilator',
    }

    for sw, command in software_used.items():
        res = subprocess.run(
            [command, '--version'],
            stdout=subprocess.PIPE
        )
        d[sw] = res.stdout.decode('utf-8').split("Copyright")[0]
        d[sw] = d[sw].replace('\n', ' ')

    os.chdir(f'{test_path}')
    platform_data = open('platform.json', 'w+')
    platform_data.write(json.dumps(d))
    platform_data.close()
    os.chdir(os.pardir)


def extract_json_results_from_file_to_file(path_to_extract, path_to_save,
                                           beg, esc):
    result_f = open(path_to_extract, mode='r')
    content = result_f.read()
    result_f.close()
    match = re.search(f'{beg}({{[\\s\\S]*}}){esc}', content, re.S)

    result_json = open(path_to_save, 'w+')
    result_json.write(match.group(1))
    result_json.close()

def arglist_to_str(arglist):
    """Make arglist into a string"""

    for arg in arglist:
        if arg == arglist[0]:
            str = arg
        else:
            str = str + ' ' + arg

    return str

def binary_benchmark_output(benchdir, binary_converter):

    dirlist = os.listdir(benchdir)

    for bench in dirlist:
        abs_b = os.path.join(benchdir,bench)
        arglist = [binary_converter, '-O', 'binary', bench, bench+'.bin']
    
        try:
            res = subprocess.run(
                arglist,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=abs_b,
                timeout=10,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            print(f'Warning: Objcopy of benchmark "{bench}" failed with ' +
                        f'return code {error.returncode}')
            print('In directory "' + abs_b + '"')
            print('Command was: {}'.format(arglist_to_str(arglist)))
            print(res.stdout.decode('utf-8'))
            print(res.stderr.decode('utf-8'))
            return False

    return True


def prepare_arguments_for_build_all(soc_kwargs, cpu_par, test_path, cpu_mhz=None, arch="sim"):
    args = []

    args.extend(["--builddir", f'../{test_path}/benchmarks'])
    args.extend(["--logdir", f'../{test_path}/logs'])
    
    args.extend(['--arch',f'{arch}'])
    args.extend("--chip generic".split())
    args.extend(f'--cpu-mhz {cpu_mhz}'.split())
    args.extend(f'--timeout 120'.split())
    args.extend(f"--cc {cpu_par['TRIPLE']}-gcc".split())

    
    cflags = f'-v -I{cpu_par["BUILDINC_DIRECTORY"]} \
-I{cpu_par["BUILDINC_DIRECTORY"]}/../libc \
-I{cpu_par["CPU_DIRECTORY"]} -I{cpu_par["SOC_DIRECTORY"]}/software/include \
-I{cpu_par["SOC_DIRECTORY"]}/software/libbase \
-std=gnu99 {cpu_par["CPUFLAGS"]} -I{cpu_par["PICOLIBC_DIRECTORY"]}/newlib/libc/tinystdio \
-I{cpu_par["PICOLIBC_DIRECTORY"]}/newlib/libc/include -O2 -ffunction-sections'
    args.extend([f'--cflags={cflags}'])
    
    user_libs = ""
    if soc_kwargs['cpu_type'] == 'blackparrot':
        user_libs += f'{cpu_par["BUILDINC_DIRECTORY"]}/../bios/mul.o '
    user_libs += f'{cpu_par["BUILDINC_DIRECTORY"]}/../bios/crt0.o \
-L{cpu_par["BUILDINC_DIRECTORY"]} -L{cpu_par["BUILDINC_DIRECTORY"]}/../libc \
-L{cpu_par["BUILDINC_DIRECTORY"]}/../libcompiler_rt \
-L{cpu_par["BUILDINC_DIRECTORY"]}/../libbase \
-lc -lcompiler_rt -lbase -lgcc'
    args.extend([f"--user-libs={user_libs}"])

    ldflags = f'-nostdlib -nodefaultlibs -nolibc -Wl,--verbose {cpu_par["CPUFLAGS"]}\
            -T{cpu_par["BUILDINC_DIRECTORY"]}/../../linker.ld -N'

    #args.extend(["--ldflags", f'"{ldflags}"'])
    args.extend([f'--ldflags={ldflags}'])

    args.extend(["--clean"])
    args.extend(["--warmup-heat", "0"])
    args.extend(["-v"])

    return args




def run_arg_parser(parser):
    parser.add_argument(
        '--cpu-type',
        type=str,
        help="CPU type to run benchmarks on",
        required=True
    )
    parser.add_argument(
        '--cpu-variant',
        type=str,
        default="standard",
        help="CPU variant to run benchmarks on\n\
When running microwatt set to standard+ghdl\n\
When running blackparrot set to sim",
    )
    parser.add_argument(
        '--output-dir',
        type=str,
    )
    parser.add_argument(
        '--threads',
        type=int,
        help="Specify number of threads for simulation to run on",
        default=1
    )
    parser.add_argument(
        '--arty',
        type=str,
        help="Run benchmarks on arty FPGA",
        default=False
    )
    parser.add_argument(
        '--integrated-sram-size',
        help="Specify how big is sram/program stack\n\
When running microwatt, blackparrot, rocket, openc906, cva6 set to at least 0x8000",
        default=0x2000
    )
    parser.add_argument(
        '--bus-data-width',
        help="Set SoC internal bus data width",
        default=32
    )
    parser.add_argument(
        "--use-cache",
        default=False,
        help="Use caches in rocket chip"
    )
    parser.add_argument(
        '--benchmark-strategy',
        help="Set to absolute, relative or combination of both, to\
test performance in given mode",
        required=True,
        choices=['absolute', 'relative', 'both']
    )


def main():
    # Reading provided arguments


    parser = argparse.ArgumentParser(
            description='Build benchmarks for given cpu type')
    run_arg_parser(parser)
    run_args = parser.parse_args()

    internal_parser = argparse.ArgumentParser()

    sim.sim_args(internal_parser)
    sim.builder_args(internal_parser)
    sim.soc_core_args(internal_parser)
    args, rest = internal_parser.parse_known_args()
    args.cpu_variant = run_args.cpu_variant
    args.integrated_sram_size = int(run_args.integrated_sram_size)
    
    if args.cpu_type == 'openc906':
        os.environ["OPENC906_DIR"] = os.path.join(os.getcwd(), 'third_party','openc906')

    soc_kwargs = sim.soc_core_argdict(args)
    test_path = f"{soc_kwargs['cpu_type']}_{soc_kwargs['cpu_variant']}" + \
                f"_{args.bus_data_width}_{args.use_cache}"

    builder_kwargs = sim.builder_argdict(args)
    builder_kwargs["output_dir"] = test_path
    builder_kwargs["compile_gateware"] = False
    soc_kwargs["opt_level"] = "O3"


    # Create software for simulated SoC
    if not args.arty:
        sim.sim_configuration(args, soc_kwargs, builder_kwargs, test_path)
    else:
        sim.arty_configuration(args, soc_kwargs, builder_kwargs, test_path)

    # Copy universal linker script
    shutil.copy2('/home/hhe07/Documents/openrisc/litex/Embench/config/sim/boards/generic/linker.ld',
                 f'./{test_path}/linker.ld')

    cpu_report = {}

    variables = f"./{test_path}/software\
/include/generated/variables.mak"
    with open(os.path.abspath(variables)) as f:
        for line in f:
            line = line.rstrip()
            test = line.split()
            if (len(test) > 1 and test[0] == "export"):
                continue
            (key, val) = line.split("=", 1)
            cpu_report[key] = val

    # Collect imformation about cpu repo and toolchain version
    for i in run_args.benchmark_strategy:
        collect_cpu_and_toolchain_data(cpu_report, i, test_path)

    # Make directories for benchamrks and logs from embench
    if not os.path.exists(f'{test_path}/benchmarks'):
        os.mkdir(f'{test_path}/benchmarks')

    if not os.path.exists(f'{test_path}/logs'):
        os.mkdir(f'{test_path}/logs')

    # Prepare namespace for build_all
    arch = "arty" if args.arty else "sim"
    cpu_mhz = 100 if args.arty else 1
    arglist = prepare_arguments_for_build_all(soc_kwargs, cpu_report, test_path, cpu_mhz, arch)
    # Build all benchmarks
    #print(test_path)
    #print(arglist)
    #quit()


    tmp = ['Embench/build_all.py']
    

    tmp.extend(arglist)
    #print(" ".join(tmp))
    #print(tmp)

    #exec(open(f"build_all.py").read(),vars(Iarglist))

    crt0_dir = os.path.join(os.path.abspath(test_path), "software/bios")
    subprocess.check_call(["make", "-C", crt0_dir, "-f", os.path.abspath('mk_crt0.mak')])

    subprocess.run(tmp)
    

    #build_all.submodule_main(arglist)
    #print(sys.argv)
    #build_all.main()

    #benchdir = f'{test_path}/benchmarks/src'
    benchdir = os.path.join(os.path.abspath(test_path),'benchmarks')
    binary_benchmark_output(os.path.join(benchdir,'src'), f'{cpu_report["TRIPLE"]}-objcopy')

    # Prepare argument namespace for benchmark
    #arglist = argparse.Namespace()
    arglist = ['Embench/benchmark_speed.py']

    arglist.extend(['--builddir', benchdir])

    arglist.extend(['--logdir', os.path.join(os.path.abspath(test_path),'logs')])

    arglist.extend(['--json-output'])

    if not args.arty:
        arglist.extend(['--target-module', 'run_litex_sim'])
    else:
        arglist.extend(['--target-module', 'run_litex_arty'])

    arglist.extend(['--timeout', '7200'])

    arglist.extend(['--baselinedir', 'baseline-data'])

    arglist.extend(['--no-json-comma'])

    #arglist.json_comma = False
    #arglist.change_dir = False
    #arglist.sim_parallel = False

    arglist.extend(f'--cpu-type {args.cpu_type}'.split())
    arglist.extend(f'--cpu-variant {args.cpu_variant}'.split())
    if not args.arty:
        arglist.extend(f'--threads {args.threads}'.split())
    arglist.extend(f'--bus-data-width {args.bus_data_width}'.split())
    arglist.extend(f'--use-cache {args.use_cache}'.split())
    arglist.extend(f'--output-dir {test_path}'.split())
    arglist.extend(f'--integrated-sram-size \
{args.integrated_sram_size}'.split())

    logs_before = set(glob.glob(f'./{test_path}/logs/speed*'))

    print(arglist)
    # Bench relative speed
    if 'relative' in run_args.benchmark_strategy:
        #arglist.absolute = 1
        arglist.extend(['--relative'])
        #benchmark_speed.submodule_main(arglist, remnant)
        subprocess.run(arglist)
        relative_result_path = f'./{test_path}/result.json'

    # Bench absolute speed
    if 'absolute' in run_args.benchmark_strategy:
        #arglist.absolute = 0
        arglist.extend(['--absolute'])
        #benchmark_speed.submodule_main(arglist, remnant)
        subprocess.run(arglist)
        absolute_result_path = f'./{test_path}/result_abs.json'

    # Bench both speed
    if 'both' in run_args.benchmark_strategy:
        arglist.absolute = 2
        #benchmark_speed.submodule_main(arglist, remnant)
        subprocess.run(arglist)
        relative_result_path = f'./{test_path}/result.json'
        absolute_result_path = f'./{test_path}/result_abs.json'

    # Extract results
    logs_path = f'./{test_path}/logs/speed*'
    logs_new = set(glob.glob(logs_path))-logs_before

    logs_new = sorted(list(logs_new))

    if 'both' in run_args.benchmark_strategy:
        extract_json_results_from_file_to_file(logs_new[0],
                                               absolute_result_path,
                                               '"speed results" :\\s*',
                                               '\\s*"speed results"')
        extract_json_results_from_file_to_file(logs_new[0],
                                               relative_result_path,
                                               '}\\s*"speed results" :\\s*',
                                               '\\s*All')

    elif 'relative' in run_args.benchmark_strategy:
        extract_json_results_from_file_to_file(logs_new[0],
                                               relative_result_path,
                                               '}\\s*"speed results" :\\s*',
                                               '\\s*All')

    elif 'absolute' in run_args.benchmark_strategy:
        extract_json_results_from_file_to_file(logs_new[0],
                                               absolute_result_path,
                                               '"speed results" :\\s*',
                                               '\\s*"speed results"')


if __name__ == '__main__':
    main()
