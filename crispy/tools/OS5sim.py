import matplotlib
matplotlib.rcParams['image.origin'] = 'lower'
matplotlib.rcParams['image.interpolation'] = 'nearest'
import numpy as np
import matplotlib.pyplot as plt
import sys
import os


# set folders
folder = '../../../crispy'
print(folder)
if folder not in sys.path: sys.path.append(folder)

from crispy.params import Params
folder = '../../crispy'
par = Params(folder)

from crispy.tools.initLogger import getLogger
log = getLogger('crispy')
from crispy.IFS import polychromeIFS
from crispy.IFS import reduceIFSMap
from crispy.tools.imgtools import scale2imgs,bowtie
from crispy.tools.image import Image
from crispy.tools.rotate import rotateCube,shiftCube
from crispy.tools.postprocessing import mf,recenter_offaxis
from crispy.tools.inputScene import adjust_krist_header
from crispy.tools.detector import averageDetectorReadout
from astropy.io import fits
import astropy.units as u
from crispy.tools.postprocessing import construct_mflib,convolved_mf


### parameters to set for simulation

lamc=660.
BW = 0.18
par.nonoise=False
sampling=2.0
par.timeframe=1000
par.Nreads = par.timeframe/100.
par.PCmode=True
par.EMStats=True
par.poisson=True
par.lifefraction = 0.0
par.lenslet_sampling=1./sampling
folder = '/Users/mrizzo/IFS/OS5_SIM_'+str(sampling)+'_t'+str(int(par.timeframe))
# folder = '/Users/mrizzo/IFS/OS5_SIM_'+str(sampling)+'_noiseless'
offaxis_psf_filename='/Users/mrizzo/IFS/OS5/offaxis/spc_offaxis_psf.fits'
OS5_files = '/Users/mrizzo/IFS/OS5/with_lowfc/'

try:
    os.makedirs(folder)
    os.makedirs(folder+'/average')
    os.makedirs(folder+'/detector')  
except OSError:
    pass
par.hdr
from crispy.tools.postprocessing import process_SPC_IFS2


signal, noise,noise_no_source,noise_no_rdi,signal_planet,signal_star,signal_no_rdi,signal_no_source = process_SPC_IFS2(par,
                    psf_time_series_folder=OS5_files,
                    offaxis_psf_filename=offaxis_psf_filename,
                    xshift=0.0,yshift=0.0,
                    lamc=lamc,BW=BW,n_ref_star_imgs=30,
                    tel_pupil_area=3.650265060424805*u.m**2,
                    IWA = 2.5,OWA = 9.,
#                     albedo_filename='Jupiter_1x_5AU_90deg.dat',
#                     planet_radius = 1.27,
#                     planet_AU = 3.6,planet_dist_pc=14.1,
                    albedo_filename='LAS_spectra_for_exospec_bright_comparison_at_90_deg_phase.txt',
                    albedo=None,
                    planet_radius = 1.0,
                    planet_AU = 3.0,planet_dist_pc=10.,
#                     target_star_T=5887*u.K, target_star_Vmag=5.03,   # 47 Uma
                    target_star_T=5778*u.K, target_star_Vmag=4.83,     # fiducial Sun at 10 pc
                    forced_inttime_ref = 10., # forced integration time for reference star individual frame
                    forced_tottime_ref = 10., # forced integration time for reference star frame group
                    pp_fact = 0.00,
                    RDI=False,
                    mflib='',
                    outdir_time_series = folder,
                    outdir_detector=folder+'/detector',
                    outdir_average=folder+'/average',
                    process_cubes=False, # this only needs to be turned to True once
                    process_offaxis_files=False, # Construct planet and off-axis star files
                    process_detector=False, # Construct IFS detector maps
                    take_averages=False,   # Take averages of these detector maps
                    subtract_dark=False,
                    normalize_cubes=True,
                    nosource=False)


np.savetxt(folder+"/average/signal.txt",signal)
np.savetxt(folder+"/average/signal_no_source.txt",signal_no_source)
np.savetxt(folder+"/average/signal_no_rdi.txt",signal_no_rdi)
np.savetxt(folder+"/average/signal_star.txt",signal_star)
np.savetxt(folder+"/average/signal_planet.txt",signal_planet)
np.savetxt(folder+"/average/noise.txt",noise)
np.savetxt(folder+"/average/noise_no_rdi.txt",noise_no_rdi)
np.savetxt(folder+"/average/noise_no_source.txt",noise_no_source)



from crispy.tools.postprocessing import SNR_spectrum
from crispy.tools.reduction import calculateWaveList
# signal = np.loadtxt(folder+"/average/signal.txt")
# noise = np.loadtxt(folder+"/average/noise.txt")
# noise = np.loadtxt(folder+"/average/noise_no_rdi.txt")
# noise = np.loadtxt(folder+"/average/noise_no_source.txt")
lam_midpts,junk = calculateWaveList(par,method='optext')
wavelist = lamc*np.linspace(1.-BW/2.,1.+BW/2.,45)
plt.figure(figsize=(20,12))
ratio_out = SNR_spectrum(lam_midpts,signal,noise,filename=par.codeRoot+"/Inputs/LAS_spectra_for_exospec_bright_comparison_at_90_deg_phase.txt",albedo=None,lam_contrast=wavelist,outfolder=par.exportDir+"/",
             FWHM=2*45./19.,FWHMdata=2,edges=1,ymargin=0.1,title='',planet_radius=1,planet_AU = 3.0)
# plt.figure(figsize=(20,12))
# ratio_out = SNR_spectrum(lam_midpts,signal_star,noise,filename=par.codeRoot+'/Inputs/Jupiter_1x_5AU_90deg.dat',lam_contrast=wavelist,outfolder=par.exportDir+"/",
#              FWHM=2*45./19.,FWHMdata=2,edges=1,ymargin=3,title='')
#np.savetxt(folder+"/average/ratio.txt",ratio_out)
plt.savefig(folder+'/average/SNR.png',dpi=300)


Ntrials=2
final_signal_cube = np.zeros((Ntrials,len(signal)))
final_signal_no_rdi_cube = np.zeros((Ntrials,len(signal)))
final_signal_star_cube = np.zeros((Ntrials,len(signal)))
final_signal_planet_cube = np.zeros((Ntrials,len(signal)))
final_signal = np.zeros(len(signal))
final_variance = np.zeros(len(signal))

import time
start = time.time()

for i in range(Ntrials):
    print "iteration",i
    signal, _,_,_,signal_planet,signal_star,signal_no_rdi,_ = process_SPC_IFS2(par,
                    psf_time_series_folder=OS5_files,
                    offaxis_psf_filename=offaxis_psf_filename,
                    xshift=0.0,yshift=0.0,
                    lamc=lamc,BW=BW,n_ref_star_imgs=30,
                    tel_pupil_area=3.650265060424805*u.m**2,
                    IWA = 2.5,OWA = 9.,
#                     albedo_filename='Jupiter_1x_5AU_90deg.dat',
#                     planet_radius = 1.27,
#                     planet_AU = 3.6,planet_dist_pc=14.1,
                    albedo_filename='LAS_spectra_for_exospec_bright_comparison_at_90_deg_phase.txt',
                    albedo=None,
                    planet_radius = 1.0,
                    planet_AU = 3.0,planet_dist_pc=10.,
#                     target_star_T=5887*u.K, target_star_Vmag=5.03,   # 47 Uma
                    target_star_T=5778*u.K, target_star_Vmag=4.83,     # fiducial Sun at 10 pc
                    forced_inttime_ref = 10., # forced integration time for reference star individual frame
                    forced_tottime_ref = 10., # forced integration time for reference star frame group
                    pp_fact = 0.00,
                    RDI=False,
                    mflib='',
                    outdir_time_series = folder,
                    outdir_detector=folder+'/detector',
                    outdir_average=folder+'/average',
                    process_cubes=False, # this only needs to be turned to True once
                    process_offaxis_files=False, # Construct planet and off-axis star files
                    process_detector=True, # Construct IFS detector maps
                    take_averages=True,   # Take averages of these detector maps
                    subtract_dark=True,
                    normalize_cubes=True,
                    nosource=False)
    final_signal += signal
    final_variance += signal**2
    final_signal_cube[i] = signal
    final_signal_no_rdi_cube[i] = signal_no_rdi
    final_signal_star_cube[i] = signal_star
    final_signal_planet_cube[i] = signal_planet
final_signal /= Ntrials
final_variance /= Ntrials
final_variance -= final_signal**2
end = time.time()
print("Time elapsed: %f" % (end - start))
np.savetxt(folder+"/average/final_signal_cube_sergi_"+str(par.timeframe)+".txt",final_signal_cube)
np.savetxt(folder+"/average/final_signal_no_rdi_cube_sergi_"+str(par.timeframe)+".txt",final_signal_no_rdi_cube)
np.savetxt(folder+"/average/final_signal_star_cube_sergi_"+str(par.timeframe)+".txt",final_signal_no_rdi_cube)
np.savetxt(folder+"/average/final_signal_planet_cube_sergi_"+str(par.timeframe)+".txt",final_signal_no_rdi_cube)


plt.figure(figsize=(20,12))
ratio_out = SNR_spectrum(lam_midpts,final_signal,np.sqrt(final_variance),filename=par.codeRoot+"/Inputs/LAS_spectra_for_exospec_bright_comparison_at_90_deg_phase.txt",albedo=None,lam_contrast=wavelist,outfolder=par.exportDir+"/",
             FWHM=2*45./19.,FWHMdata=2,edges=1,ymargin=0.1,title='',planet_radius=1,planet_AU = 3.0)
plt.savefig(folder+'/average/SNR_over_trials.png',dpi=300)
