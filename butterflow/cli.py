# Author: Duong Pham
# Copyright 2015

import os
import sys
import argparse
import math
import string
from butterflow import avinfo, motion, ocl, settings
from butterflow.render import Renderer
from butterflow.sequence import VideoSequence, RenderSubregion

NO_VIDEO_SPECIFIED = 'Error: no input file specified'


def main():
    par = argparse.ArgumentParser(usage='butterflow [options] [video]',
                                  add_help=False)
    req = par.add_argument_group('Required arguments')
    gen = par.add_argument_group('General options')
    dsp = par.add_argument_group('Display options')
    vid = par.add_argument_group('Video options')
    mux = par.add_argument_group('Muxing options')
    fgr = par.add_argument_group('Advanced options')

    req.add_argument('video', type=str, nargs='?', default=None,
                     help='Specify the input video')

    gen.add_argument('-h', '--help', action='help',
                     help='Show this help message and exit')
    gen.add_argument('--version', action='store_true',
                     help='Show program\'s version number and exit')
    gen.add_argument('-d', '--devices', action='store_true',
                     help='Show detected OpenCL devices and exit')
    gen.add_argument('-sw', action='store_true',
                     help='Set to force software rendering')
    gen.add_argument('-c', '--cache', action='store_true',
                     help='Show cache information and exit')
    gen.add_argument('--rm-cache', action='store_true',
                     help='Set to clear the cache and exit')
    gen.add_argument('-prb', '--probe', action='store_true',
                     help='Show media file information and exit')
    gen.add_argument('-v', '--verbose', action='store_true',
                     help='Set to increase output verbosity')

    dsp.add_argument('-np', '--no-preview', action='store_false',
                     help='Set to disable video preview')
    dsp.add_argument('-a', '--add-info', action='store_true',
                     help='Set to embed debugging info into the output '
                          'video')
    dsp.add_argument('-tt', '--text-type',
                     choices=['light', 'dark', 'stroke'],
                     default=settings.default['text_type'],
                     help='Specify text type for debugging info, '
                     '(default: %(default)s)')
    dsp.add_argument('-mrk', '--mark-frames', action='store_true',
                     help='Set to mark interpolated frames')

    vid.add_argument('-o', '--output-path', type=str,
                     default=settings.default['out_path'],
                     help='Specify path to the output video')
    vid.add_argument('-r', '--playback-rate', type=str,
                     help='Specify the playback rate as an integer or a '
                     'float. Fractional forms are acceptable. To use a '
                     'multiple of the source video\'s rate, follow a number '
                     'with `x`, e.g., "2x" will double the frame rate. The '
                     'original rate will be used by default if nothing is '
                     'specified.')
    vid.add_argument('-s', '--sub-regions', type=str,
                     help='Specify rendering subregions in the form: '
                     '"a=TIME,b=TIME,TARGET=VALUE" where TARGET is either '
                     '`fps`, `dur`, `spd`. Valid TIME syntaxes are [hr:m:s], '
                     '[m:s], [s], [s.xxx], or `end`, which signifies to the '
                     'end the video. You can specify multiple subregions by '
                     'separating them with a colon `:`. A special region '
                     'format that conveniently describes the entire clip is '
                     'available in the form: "full,TARGET=VALUE".')
    vid.add_argument('-t', '--trim-regions', action='store_true',
                     help='Set to trim subregions that are not explicitly '
                          'specified')
    vid.add_argument('-vs', '--video-scale', type=str,
                     default=str(settings.default['video_scale']),
                     help='Specify output video size in the form: '
                     '"WIDTH:HEIGHT" or by using a factor. To keep the '
                     'aspect ratio only specify one component, either width '
                     'or height, and set the other component to -1, '
                     '(default: %(default)s)')
    vid.add_argument('-l', '--lossless', action='store_true',
                     help='Set to use lossless encoding settings')
    vid.add_argument('-sm', '--smooth-motion', action='store_true',
                     help='Set to tune for smooth motion. This mode favors '
                     'accuracy and artifact-less frames above all and will '
                     'emphasize blending over warping points.')

    mux.add_argument('-mux', action='store_true',
                     help='Set to mux the source audio with the output '
                     'video. Audio may not be in sync with the final video if '
                     'speed has been altered during the rendering process.')

    fgr.add_argument('--fast-pyr', action='store_true',
                     help='Set to use fast pyramids')
    fgr.add_argument('--pyr-scale', type=float,
                     default=settings.default['pyr_scale'],
                     help='Specify pyramid scale factor, '
                     '(default: %(default)s)')
    fgr.add_argument('--levels', type=int,
                     default=settings.default['levels'],
                     help='Specify number of pyramid layers, '
                     '(default: %(default)s)')
    fgr.add_argument('--winsize', type=int,
                     default=settings.default['winsize'],
                     help='Specify average window size, '
                     '(default: %(default)s)')
    fgr.add_argument('--iters', type=int,
                     default=settings.default['iters'],
                     help='Specify number of iterations at each pyramid '
                     'level, (default: %(default)s)')
    fgr.add_argument('--poly-n', type=int,
                     choices=settings.default['poly_n_choices'],
                     default=settings.default['poly_n'],
                     help='Specify size of pixel neighborhood, '
                     '(default: %(default)s)')
    fgr.add_argument('--poly-s', type=float,
                     default=settings.default['poly_s'],
                     help='Specify standard deviation to smooth derivatives, '
                     '(default: %(default)s)')
    fgr.add_argument('-ff', '--flow-filter', choices=['box', 'gaussian'],
                     default=settings.default['flow_filter'],
                     help='Specify which filter to use for optical flow '
                     'estimation, (default: %(default)s)')

    # add a space to args that start with a `-` char to avoid an unexpected
    # argument error. needed for the `--video-scale` option
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit():
            sys.argv[i] = ' ' + arg

    args = par.parse_args()

    import logging
    logging.basicConfig(level=settings.default['loglevel_a'],
                        format='%(levelname)-7s: %(message)s')

    log = logging.getLogger('butterflow')
    if args.verbose:
        log.setLevel(settings.default['loglevel_b'])

    if args.version:
        from butterflow.__init__ import __version__
        print('butterflow version %s' % __version__)
        return 0

    if args.cache:
        print_cache_info()
        return 0

    if args.rm_cache:
        rm_cache()
        print('cache deleted, done.')
        return 0

    if args.devices:
        ocl.print_ocl_devices()
        return 0

    if args.video is None:
        print(NO_VIDEO_SPECIFIED)
        return 1

    if not os.path.exists(args.video):
        print('Error: file does not exist at path')
        return 1

    if args.probe:
        if args.video:
            try:
                avinfo.print_av_info(args.video)
            except Exception as e:
                print('Error: %s' % e)
        else:
            print(NO_VIDEO_SPECIFIED)
        return 0

    try:
        vid_info = avinfo.get_av_info(args.video)
    except Exception as e:
        print('Error: %s' % e)
        return 1

    if not vid_info['v_stream_exists']:
        print('Error: no video stream detected')
        return 1

    try:
        sequence = sequence_from_str(vid_info['duration'],
                                     vid_info['frames'], args.sub_regions)
    except Exception as e:
        print('Bad subregion string: %s' % e)
        return 1

    src_rate = (vid_info['rate_n'] * 1.0 /
                vid_info['rate_d'])
    try:
        rate = rate_from_str(args.playback_rate, src_rate)
    except Exception as e:
        print('Bad playback rate: %s' % e)
        return 1
    if rate < src_rate:
        log.warning('rate=%s < src_rate=%s', rate, src_rate)

    try:
        w, h = w_h_from_str(args.video_scale, vid_info['w'], vid_info['h'])
    except Exception as e:
        print('Bad video scale: %s' % e)
        return 1

    have_ocl = ocl.compat_ocl_device_available()
    use_sw = args.sw or not have_ocl

    if use_sw:
        log.warning('not using opencl accelerated methods')

    # make functions that will generate flows and interpolate frames
    from cv2 import calcOpticalFlowFarneback as sw_optical_flow
    farneback_method = sw_optical_flow if use_sw else \
        motion.ocl_farneback_optical_flow
    flags = 0
    if args.flow_filter == 'gaussian':
        import cv2
        flags = cv2.OPTFLOW_FARNEBACK_GAUSSIAN

    if args.smooth_motion:
        args.poly_s = 0.1

    # don't make the function with `lambda` because `draw_debug_text` will need
    # to retrieve kwargs with the `inspect` module
    def flow_function(x, y, pyr=args.pyr_scale, l=args.levels, w=args.winsize,
                      i=args.iters, polyn=args.poly_n, polys=args.poly_s,
                      fast=args.fast_pyr, filt=flags):
        if farneback_method == motion.ocl_farneback_optical_flow:
            return farneback_method(x, y, pyr, l, w, i, polyn, polys, fast, filt)
        else:
            return farneback_method(x, y, pyr, l, w, i, polyn, polys, filt)

    from butterflow.interpolate import sw_interpolate_flow
    interpolate_function = sw_interpolate_flow if use_sw else \
        motion.ocl_interpolate_flow

    renderer = Renderer(
        args.output_path,
        vid_info,
        sequence,
        rate,
        flow_function,
        interpolate_function,
        w,
        h,
        args.lossless,
        args.trim_regions,
        args.no_preview,
        args.add_info,
        args.text_type,
        args.mark_frames,
        args.mux)

    motion.set_num_threads(settings.default['ocv_threads'])

    try:
        # time how long it takes to render. timeit will turn off gc, must turn
        # it back on to maximize performance re-nable it in the setup function
        import timeit
        tot_time = timeit.timeit(renderer.render,
                                 setup='import gc;gc.enable()',
                                 number=1)  # only run once
        tot_time /= 60  # time in minutes

        new_sz = human_sz(float(os.path.getsize(args.output_path)))

        print('Frames written:')
        print(' {} real, {} interpolated, {} duped, {} dropped'.format(
            renderer.tot_src_frs,
            renderer.tot_frs_int,
            renderer.tot_frs_dup,
            renderer.tot_frs_drp))
        print(' write ratio: {}/{}, ({:.2f}%)'.format(
            renderer.tot_frs_wrt,
            renderer.tot_tgt_frs,
            renderer.tot_frs_wrt * 100.0 / renderer.tot_tgt_frs))
        print(' out size: {}'.format(new_sz))
        print('butterflow took {:.3g} minutes, done.'.format(tot_time))
    except (KeyboardInterrupt, SystemExit):
        log.warning('stopped early, files were left in the cache')
        log.warning('recoverable @ {}'.format(settings.default['tmp_dir']))
        return 1
    except Exception:
        return 1


def human_sz(nbytes):
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    if nbytes == 0:
        return '0 B'
    i = 0
    while nbytes >= 1024 and i < len(suffixes) - 1:
        nbytes /= 1024.
        i += 1
    f = ('{:.2f}'.format(nbytes)).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])


def print_cache_info():
    # clb_dir exists inside the tmp_dir
    cache_dir = settings.default['tmp_dir']
    num_files = 0
    sz = 0
    for dirpath, dirnames, filenames in os.walk(cache_dir):
        # ignore the clb_dir
        if dirpath == settings.default['clb_dir']:
            continue
        for f in filenames:
            num_files += 1
            fp = os.path.join(dirpath, f)
            sz += os.path.getsize(fp)
    sz = human_sz(float(sz))
    print('{} files, {}'.format(num_files, sz))
    print('cache @ %s' % cache_dir)


def rm_cache():
    # delete contents of the cache, including the clb_dir
    cache_dir = settings.default['tmp_dir']
    if os.path.exists(cache_dir):
        import shutil
        shutil.rmtree(cache_dir)


def validate_chars_in_set(ch_set):
    # decorator, ensures all chars in string args are in a char set
    def wrapper(f):
        def wrapped_f(*args, **kwargs):
            strs = []
            for a in args:
                if isinstance(a, str):
                    strs.append(a)
            for k, v in kwargs:
                if isinstance(v, str):
                    strs.append(v)
            for s in strs:
                for i, ch in enumerate(s):
                    if ch not in ch_set:
                        msg = 'unknown char `{}` at idx={}'.format(ch, i)
                        raise ValueError(msg)
            return f(*args, **kwargs)
        return wrapped_f
    return wrapper


@validate_chars_in_set(string.digits + ':-.')
def w_h_from_str(string, source_width, source_height):
    if ':' in string:  # used `w:h` syntax
        w, h = string.split(':')
        w = int(w)
        h = int(h)
        if w < -1 or h < -1:
            raise ValueError('unknown negative component')
        # keep aspect ratio if either component is -1
        if w == -1 and h == -1:  # ffmpeg allows this so we should too
            return source_width, source_height
        else:
            if w == -1:
                w = int(h * source_width / source_height) & ~1  # round to even
            elif h == -1:
                h = int(w * source_height / source_width) & ~1
    elif float(string) != 1.0:  # using a singlular int or float
        # round to nearest even number
        even_pixel = lambda x: \
            int(math.floor(x * float(string) / 2) * 2)
        w = even_pixel(source_width)
        h = even_pixel(source_height)
    else:  # use source w,h by default
        w = source_width
        h = source_height
    # w and h must be divisible by 2 for yuv420p outputs
    # don't auto round when using the `w:h` syntax (with no -1 components)
    # because the user may not expect the changes
    if math.fmod(w, 2) != 0 or math.fmod(h, 2) != 0:
        raise ValueError('components not divisible by two')
    return w, h


@validate_chars_in_set(string.digits + '/x.')
def rate_from_str(string, source_rate):
    if string is None:
        return source_rate
    if '/' in string:  # got a fraction
        # can't create Fraction object then cast to a float because it
        # doesn't support non-rational numbers
        n, d = string.split('/')
        rate = float(n) / float(d)
    elif 'x' in string:  # used the "multiple of" syntax (e.g. `2x`)
        rate = float(string.replace('x', ''))
        rate = rate * source_rate
    else:  # got a singular integer or float
        rate = float(string)
    if rate <= 0:
        raise ValueError('invalid frame rate value')
    return rate


@validate_chars_in_set(string.digits + ':.')
def time_str_to_ms(time):
    # converts a time str to milliseconds
    # time str syntax:
    # [hrs:mins:secs.xxx], [mins:secs.xxx], [secs.xxx]
    hr = 0
    minute = 0
    sec = 0
    time = time.strip()
    if time == '':
        raise ValueError('no time specified')
    if time.count(':') > 2:
        raise ValueError('invalid time format')
    val = time.split(':')
    n = len(val)
    # going backwards in the list
    # get secs.xxx portion
    if n >= 1:
        if val[-1] != '':
            sec = float(val[-1])
    # get mins portion
    if n >= 2:
        if val[-2] != '':
            minute = float(val[-2])
    # get hrs portion
    if n == 3:
        if val[-3] != '':
            hr = float(val[-3])
    return (hr * 3600 + minute * 60 + sec) * 1000.0


@validate_chars_in_set(string.digits + '=./' + 'spdurf')
def parse_tval_str(string):
    # extract values from TARGET=VALUE string
    # target can be fps, dur, spd
    tgt = string.split('=')[0]  # the `TARGET` portion
    val = string.split('=')[1]  # the `VALUE` portion
    if tgt == 'fps':
        val = rate_from_str(val, -1)
    elif tgt == 'dur':
        val = float(val) * 1000  # duration in ms
    elif tgt == 'spd':
        val = float(val)
    else:
        raise ValueError('invalid target')
    return tgt, val


@validate_chars_in_set(string.digits + 'ab,=./:' + 'spdurf')
def sub_from_str(string):
    # returns a subregion from string
    # input syntax:
    # a=<time>,b=<time>,TARGET=VALUE
    val = string.split(',')
    a = val[0].split('=')[1]  # the `a=` portion
    b = val[1].split('=')[1]  # the `b=` portion
    c = val[2]  # the `TARGET=VALUE` portion
    ta = time_str_to_ms(a)
    tb = time_str_to_ms(b)
    if ta > tb:
        raise ValueError('a > b')  # start time > end time
    sub = RenderSubregion(ta, tb)
    tgt, val = parse_tval_str(c)
    setattr(sub, tgt, val)
    return sub


@validate_chars_in_set(string.digits + ',=./' + 'spdurfl')
def sub_from_str_full_key(string, duration):
    # returns a subregion from string with the `full` keyword
    # input syntax:
    # full,TARGET=VALUE
    val = string.split(',')
    if val[0] == 'full':
        # create a subregion from [0, duration]
        sub = RenderSubregion(0, float(duration))
        tgt, val = parse_tval_str(val[1])
        setattr(sub, tgt, val)
        return sub
    else:
        raise ValueError('`full` key not found')


@validate_chars_in_set(string.digits + 'ab,=./:' + 'spdurfen')
def sub_from_str_end_key(string, duration):
    # returns a subregion from string with the `end` keyword
    # input syntax:
    # a=<time>,b=end,TARGET=VALUE
    val = string.split(',')
    b = val[1].split('=')[1]  # the `b=` portion
    if b == 'end':
        # replace the `end` with the duration of the video in seconds. the
        # duration will be converted to ms automatically
        string = string.replace('end', str(duration / 1000.0))
        return sub_from_str(string)
    else:
        raise ValueError('`end` key not found')


@validate_chars_in_set(string.digits + 'ab,=./:' + 'spdurflen')
def sequence_from_str(duration, frames, string):
    # return a vid sequence from -s <subregion>:<subregion>...
    seq = VideoSequence(duration, frames)
    if string is None:
        return seq
    # check for bad separators
    # if there is a char before `a` that is not `:` like `,`
    def find_char(str, ch):
        idxs = []
        for i, ltr in enumerate(str):
            if ltr == ch:
                idxs.append(i)
        return idxs
    idxs_of_a = find_char(string, 'a')
    for i in idxs_of_a:
        if i == 0:
            continue
        else:
            ch_before_a = string[i - 1]
            if ch_before_a != ':':
                msg = 'invalid separator `{}` at idx={}'.format(ch_before_a, i)
                raise ValueError(msg)
    # look for `:a` which is the start of a new subregion
    newsubstrs = []
    substrs = string.split(':a')
    if len(substrs) > 1:
        # replace `a` character that was stripped when split
        for substr in substrs:
            if not substr.startswith('a'):
                newsubstrs.append('a' + substr)
            else:
                newsubstrs.append(substr)
        substrs = newsubstrs
    for substr in substrs:
        sub = None
        # has the full key
        if 'full' in substr:
            sub = sub_from_str_full_key(substr, duration)
        # has the end key
        elif 'end' in substr:
            sub = sub_from_str_end_key(substr, duration)
        else:
            sub = sub_from_str(substr)
        seq.add_subregion(sub)
    return seq
