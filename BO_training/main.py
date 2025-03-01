from test_funcs import *
from mixed_test_func import *
from bo.optimizer import Optimizer
from bo.optimizer_mixed import MixedOptimizer
import logging
import argparse
import os,pdb
import pickle
import pandas as pd
import time, datetime
from test_funcs.random_seed_config import *

# Set up the objective function
parser = argparse.ArgumentParser('Run Experiments')
parser.add_argument('-p', '--problem', type=str, default='pest')
parser.add_argument('--max_iters', type=int, default=150, help='Maximum number of BO iterations.')
parser.add_argument('--lamda', type=float, default=1e-6, help='the noise to inject for some problems')
parser.add_argument('--batch_size', type=int, default=1, help='batch size for BO.')
parser.add_argument('--n_trials', type=int, default=20, help='number of trials for the experiment')
parser.add_argument('--n_init', type=int, default=20, help='number of initialising random points')
parser.add_argument('--save_path', type=str, default='output/', help='save directory of the log files')
parser.add_argument('--ard', action='store_true', help='whether to enable automatic relevance determination')
parser.add_argument('--cawarmup', type=int, default=0, help='whether to use coordinate ascent to warm up the process')
parser.add_argument('-a', '--acq', type=str, default='ei', help='choice of the acquisition function.')
parser.add_argument('--random_seed_objective', type=int, default=20, help='The default value of 20 is provided also in COMBO')
parser.add_argument('-d', '--debug', action='store_true', help='Whether to turn on debugging mode (a lot of output will'
                                                               'be generated).')
parser.add_argument('--no_save', action='store_true', help='If activated, do not save the current run into a log folder.')
parser.add_argument('--seed', type=int, default=None, help='**initial** seed setting')
parser.add_argument('-k', '--kernel_type', type=str, default=None, help='specifies the kernel type')
parser.add_argument('--infer_noise_var', action='store_true')
parser.add_argument('--bamid',type=str,default="",help='ID of the bam file')
parser.add_argument('--scallop_bam',type=str, default=None, help='the input bam file of Scallop')
parser.add_argument('--scallop_lib_type',type=str,default='empty',help='library type of the Scallop input')
parser.add_argument('--scallop_ref',type=str,default='GRCh38',help='reference name of the Scallop input')
parser.add_argument('--scallop_path',type=str,default='',help='The path of the software scallop')
parser.add_argument('--sub_sample',type=float,default=1.0,help='Sampling rate of the scallop')

args = parser.parse_args()
options = vars(args)
print(options)
assert args.max_iters >= args.n_init

if args.debug:
    logging.basicConfig(level=logging.INFO)

# Sanity checks
assert args.acq in ['ucb', 'ei', 'thompson'], 'Unknown acquisition function choice ' + str(args.acq)

#pdb.set_trace()
if not os.path.exists(args.save_path):
    os.makedirs(args.save_path)

for t in range(args.n_trials):

    kwargs = {}
    #pdb.set_trace()
    if args.random_seed_objective is not None:
        assert 1 <= int(args.random_seed_objective) <= 25
        args.random_seed_objective -= 1

    if args.problem == 'pest':
        random_seed_ = sorted(generate_random_seed_pestcontrol())[args.random_seed_objective]
        f = PestControl(random_seed=random_seed_)
        kwargs = {
            'length_max_discrete': 25,
            'length_init_discrete': 20,
        }
    elif args.problem == 'Scallop':
        f = Scallop(args.scallop_bam,boundary_fold = 0,ref_file="/mnt/disk69/user/yihangs/hyper_tuning/test/"+args.scallop_ref+".gtf",library_type=args.scallop_lib_type)
        kwargs = {'failtol':18, 'guided_restart':False,'length_init_discrete':20, 'length_min':0.02}
    elif args.problem == 'func2C':
        f = Func2C(lamda=args.lamda)
    elif args.problem == 'func2C_testDiscrete':
        f = Func2C_testDiscrete(lamda=args.lamda)
        kwargs = {'guided_restart':False}
    elif args.problem == 'func3C':
        f = Func3C(lamda=args.lamda)
        kwargs = {'failtol':10, 'guided_restart':False}
    elif args.problem == 'Func3C_testDiscrete':
        f = Func3C_testDiscrete(lamda=args.lamda)
        kwargs = {'guided_restart':False,'failtol':10}
    elif args.problem == 'ackley53':
        f = Ackley53(lamda=args.lamda)
        kwargs = {
            'length_max_discrete': 50,
            'length_init_discrete': 30,
        }
    elif args.problem == 'MaxSAT60':
        f = MaxSAT60()
        kwargs = {
            'length_max_discrete': 60,
        }
    elif args.problem == 'xgboost-mnist':
        f = XGBoostOptTask(lamda=args.lamda, task='mnist', seed=args.seed)
    else:
        raise ValueError('Unrecognised problem type %s' % args.problem)

    n_categories = f.n_vertices
    problem_type = f.problem_type

    print('----- Starting trial %d / %d -----' % ((t + 1), args.n_trials))
    res = pd.DataFrame(np.nan, index=np.arange(int(args.max_iters*args.batch_size)),
                       columns=['Index', 'LastValue', 'BestValue', 'Time'])
    if args.infer_noise_var: noise_variance = None
    else: noise_variance = f.lamda if hasattr(f, 'lamda') else None

    if args.kernel_type is None:  kernel_type = 'mixed' if problem_type == 'mixed' else 'transformed_overlap'
    else: kernel_type = args.kernel_type
    if args.cawarmup > 0:
        if(args.sub_sample<1):
            cmd = 'perl ca_warmup.pl ./warmup_' + args.bamid + "_subsample_" + str(args.sub_sample) + " " + f.bam_file + " " + f.library_type + " " + f.ref_file + " 1 " + str(args.cawarmup) + " " + args.scallop_path + " " + str(args.sub_sample)
        else:
            cmd = 'perl ca_warmup.pl ./warmup_' + args.bamid + "_subsample_" + str(args.sub_sample) + " " + f.bam_file + " " + f.library_type + " " + f.ref_file + " 1 " + str(args.cawarmup) + " " + args.scallop_path
        print(cmd)
        os.system(cmd)
        x_next,y_next = read_warmup_info("./warmup_" + args.bamid + "_subsample_" + str(args.sub_sample) + "/")
        #adjust the search space
        #pdb.set_trace()
        f.ub = np.maximum(x_next[np.array(y_next).argmin()][2:]*2,f.ub)
        #pdb.set_trace()

    if problem_type == 'mixed':
        optim = MixedOptimizer(f.config, f.lb, f.ub, f.continuous_dims, f.categorical_dims, int_constrained_dims=f.int_constrained_dims,
                               default_x=f.default, n_init=args.n_init, use_ard=args.ard, acq=args.acq,
                               kernel_type=kernel_type,
                               noise_variance=noise_variance,
                               **kwargs)
    else:
        optim = Optimizer(f.config, default_x=f.default, n_init=args.n_init, use_ard=args.ard, acq=args.acq,
                          kernel_type=kernel_type,
                          noise_variance=noise_variance, **kwargs)

    T_array = []
    start = time.time()
    #pdb.set_trace()
    if args.cawarmup >0:
        _ = optim.suggest(args.batch_size)
        #cmd = 'perl ca_warmup.pl ./warmup_' + args.bamid + " " + f.bam_file + " " + f.library_type + " " + f.ref_file + " 1 " + str(args.n_init)
        #print(cmd)
        #os.system(cmd)
        #x_next,y_next = read_warmup_info("./warmup_" + args.bamid + "/")
        # adjust the search space
        #x_next,y_next = coordinate_ascent_warmup(f,fold_step=5,iterations=args.n_init)
        optim.observe(x_next, y_next)
        n_init_num = len(y_next)
    else:
        x_next = optim.suggest(args.batch_size)
        y_next = f.compute(x_next, normalize=f.normalize,scallop_path=args.scallop_path,subsamp=args.sub_sample)
        optim.observe(x_next, y_next)
        n_init_num = args.n_init
    end = time.time()
    T_array.append(end - start)
    for i in range(args.max_iters-n_init_num):
        #pdb.set_trace()
        start = time.time()
        x_next = optim.suggest(args.batch_size)
        y_next = f.compute(x_next, normalize=f.normalize,scallop_path=args.scallop_path,subsamp=args.sub_sample)
        optim.observe(x_next, y_next)
        end = time.time()
        T_array.append(end - start)
        if f.normalize:
            Y = np.array(optim.casmopolitan.fX) * f.std + f.mean
        else:
            Y = np.array(optim.casmopolitan.fX)
        if optim.casmopolitan.length <= optim.casmopolitan.length_min or optim.casmopolitan.length_discrete <= optim.casmopolitan.length_min_discrete:
            #optim.restart()
            break
        '''
        if Y[:i].shape[0]:
            # sequential
            if args.batch_size == 1:
                res.iloc[i, :] = [i, float(Y[-1]), float(np.min(Y[:i])), end-start]
            # batch
            else:
                for idx, j in enumerate(range(i*args.batch_size, (i+1)*args.batch_size)):
                    res.iloc[j, :] = [j, float(Y[-idx]), float(np.min(Y[:i*args.batch_size])), end-start]
            # x_next = x_next.astype(int)
            argmin = np.argmin(Y[:i*args.batch_size])

            print('Iter %d, Last X %s; fX:  %.4f. X_best: %s, fX_best: %.4f'
                  % (i, x_next.flatten(),
                     float(Y[-1]),
                     ''.join([str(int(i)) for i in optim.casmopolitan.X[:i * args.batch_size][argmin].flatten()]),
                     Y[:i*args.batch_size][argmin]))
        '''
        if Y[:i+args.n_init].shape[0]:
            argmin = np.argmin(Y)
            print('Iter %d, Last X %s; fX:  %.4f. X_best: %s, fX_best: %.4f'
                  % (i, x_next.flatten(),
                     float(Y[-1]),
                     ''.join([str(int(i)) for i in optim.casmopolitan.X[argmin].flatten()]),
                     Y[argmin]))
    np.save(args.save_path + "/" + args.problem + "_wall_clock_"+str(t+1)+".npy",np.array(T_array))
    np.save(args.save_path + "/" + args.problem + "_X_"+str(t+1)+".npy",optim.casmopolitan.X)
    np.save(args.save_path + "/" + args.problem + "_Y_"+str(t+1)+".npy",Y)

    if args.seed is not None:
        args.seed += 1
