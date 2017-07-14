#!/usr/bin/env python

import numpy as np
try:
    from astropy.io import fits as pyf
except:
    import pyfits as pyf
from rotate import Rotate
from initLogger import getLogger
log = getLogger('crispy')
import matplotlib.pyplot as plt
from detutils import frebin
from scipy import ndimage
from scipy.special import erf
from spectrograph import distort
from locate_psflets import initcoef,transform


def processImagePlane(par,imagePlane):
    '''
    Function processImagePlane
    
    Rotates an image or slice, and rebins in a flux-conservative way
    on an array of lenslets, using the plate scale provided in par.pixperlenslet.
    Each pixel represents the flux within a lenslet. Starts by padding the original
    image to avoid cropping edges when rotating. This step necessarily involves an
    interpolation, so one needs to be cautious.
    
    Parameters
    ----------
    par :   Parameters instance
            Contains all IFS parameters
    imagePlane : 2D array
            Input slice to IFS sim, first dimension of data is wavelength

    Returns
    -------
    imagePlaneRot : 2D array
            Rotated image plane on same sampling as original.
    '''
    
    paddedImagePlane = np.zeros((int(imagePlane.shape[0]*np.sqrt(2)),int(imagePlane.shape[1]*np.sqrt(2))))
    
    xdim,ydim = paddedImagePlane.shape
    xpad = xdim-imagePlane.shape[0]
    ypad = ydim-imagePlane.shape[1]
    xpad //=2
    ypad //=2
    paddedImagePlane[xpad:-xpad,ypad:-ypad] = imagePlane
    
    imagePlaneRot = Rotate(paddedImagePlane,par.philens,clip=False)
    
    ###################################################################### 
    # Flux conservative rebinning
    ###################################################################### 
    newShape = (int(imagePlaneRot.shape[0]/par.pixperlenslet),int(imagePlaneRot.shape[1]/par.pixperlenslet))
    imagePlaneRot = frebin(imagePlaneRot,newShape)
    log.debug('Input plane is %dx%d' % imagePlaneRot.shape)
    
    return imagePlaneRot



def propagateLenslets(par,imageplane, lam1, lam2, hires_arrs=None, lam_arr=None, 
                     upsample=5, nlam=10,npix=13):
    """
    """
#     oldsum = np.sum(imageplane)
    padding = 10
    ydim,xdim = imageplane.shape
    
    xindx = np.arange(-xdim//2, -xdim//2+xdim)
    xindx, yindx = np.meshgrid(xindx, xindx)
    
#     val = imageplane[jcoord+imageplane.shape[0]//2,icoord+imageplane.shape[0]//2]

    image = np.zeros((par.npix + 2*padding, par.npix + 2*padding))
    x = np.arange(image.shape[0])
    x, y = np.meshgrid(x, x)

    dloglam = (np.log(lam2) - np.log(lam1))/nlam
    loglam = np.log(lam1) + dloglam/2. + np.arange(nlam)*dloglam

    for lam in np.exp(loglam):


#         if not par.gaussian:
        ################################################################
        # Build the appropriate average hires image by averaging over
        # the nearest wavelengths.  Then apply a spline filter to the
        # interpolated high resolution PSFlet images to avoid having
        # to do this later, saving a factor of a few in time.
        ################################################################
    
        if (hires_arrs is None) or (lam_arr is None):
            log.error('No template PSFLets given!')
            return
        else:
            hires = np.zeros((hires_arrs[0].shape))
            if lam <= np.amin(lam_arr):
                hires[:] = hires_arrs[0]
            elif lam >= np.amax(lam_arr):
                hires[:] = hires_arrs[-1]
            else:
                i1 = np.amax(np.arange(len(lam_arr))[np.where(lam > lam_arr)])
                i2 = i1 + 1
                hires = hires_arrs[i1]*(lam - lam_arr[i1])/(lam_arr[i2] - lam_arr[i1])
                hires += hires_arrs[i2]*(lam_arr[i2] - lam)/(lam_arr[i2] - lam_arr[i1])

            for i in range(hires.shape[0]):
                for j in range(hires.shape[1]):
                    hires[i, j] = ndimage.spline_filter(hires[i, j])
        

        ################################################################
        # Run through lenslet centroids at this wavelength using the
        # fitted coefficients in psftool to get the centroids.  For
        # each centroid, compute the weights for the four nearest
        # regions on which the high-resolution PSFlets have been made.
        # Interpolate the high-resolution PSFlets and take their
        # weighted average, adding this to the image in the
        # appropriate place.
        ################################################################

        ################################################################
        # NOTE THE NEGATIVE SIGN TO PHILENS
        # here is where one could import any kind of polynomial mapping
        # and introduce distortions
        ################################################################
        order = 3
#         dispersion = par.npixperdlam*par.R*(lam-par.FWHMlam)/par.FWHMlam
        dispersion = par.npixperdlam*par.R*np.log(lam/par.FWHMlam)
        coef = initcoef(order, scale=par.pitch/par.pixsize, phi=-par.philens, x0=0, y0=dispersion)
        ycen, xcen = transform(xindx, yindx, order, coef)
        xcen+=par.npix//2
        ycen+=par.npix//2

        xcen += padding
        ycen += padding
        xindx = np.reshape(xindx,-1)
        yindx = np.reshape(yindx,-1)
        xcen = np.reshape(xcen, -1)
        ycen = np.reshape(ycen, -1)
        for i in range(xcen.shape[0]):
            if not (xcen[i] > npix//2 and xcen[i] < image.shape[0] - npix//2 and 
                    ycen[i] > npix//2 and ycen[i] < image.shape[0] - npix//2):
                continue
                
            # these are the coordinates of the lenslet within the image plane
            Ycoord = yindx[i] + imageplane.shape[0]//2
            Xcoord = xindx[i] + imageplane.shape[1]//2
            
            if not (Xcoord>0 and Xcoord<imageplane.shape[1] and Ycoord>0 and Ycoord<imageplane.shape[0]):
                continue
            
            val = imageplane[Ycoord,Xcoord]
            
            # if the value is 0, don't waste time
            if val==0.0:
                continue
                
            # central pixel -> npix*upsample//2
            iy1 = int(ycen[i]) - npix//2
            iy2 = iy1 + npix
            ix1 = int(xcen[i]) - npix//2
            ix2 = ix1 + npix
            
            # Now find the closest high-resolution PSFs from a library
            yinterp = (y[iy1:iy2, ix1:ix2] - ycen[i])*upsample + upsample*npix/2
            xinterp = (x[iy1:iy2, ix1:ix2] - xcen[i])*upsample + upsample*npix/2
        
            
            if hires.shape[0]==1 and hires.shape[1]==1:
                image[iy1:iy2, ix1:ix2] += val*ndimage.map_coordinates(hires[0,0], [yinterp, xinterp], prefilter=False)/nlam
            else:
                x_hires = xcen[i]*1./image.shape[1]
                y_hires = ycen[i]*1./image.shape[0]
        
                x_hires = x_hires*hires_arrs[0].shape[1] - 0.5
                y_hires = y_hires*hires_arrs[0].shape[0] - 0.5
        
                totweight = 0
        
                if x_hires <= 0:
                    i1 = i2 = 0
                elif x_hires >= hires_arrs[0].shape[1] - 1:
                    i1 = i2 = hires_arrs[0].shape[1] - 1
                else:
                    i1 = int(x_hires)
                    i2 = i1 + 1

                if y_hires < 0:
                    j1 = j2 = 0
                elif y_hires >= hires_arrs[0].shape[0] - 1:
                    j1 = j2 = hires_arrs[0].shape[0] - 1
                else:
                    j1 = int(y_hires)
                    j2 = j1 + 1


        
                ##############################################################
                # Bilinear interpolation by hand.  Do not extrapolate, but
                # instead use the nearest PSFlet near the edge of the
                # image.  The outer regions will therefore have slightly
                # less reliable PSFlet reconstructions.  Then take the
                # weighted average of the interpolated PSFlets.
                ##############################################################
                weight22 = max(0, (x_hires - i1)*(y_hires - j1))
                weight12 = max(0, (x_hires - i1)*(j2 - y_hires))
                weight21 = max(0, (i2 - x_hires)*(y_hires - j1))
                weight11 = max(0, (i2 - x_hires)*(j2 - y_hires))
                totweight = weight11 + weight21 + weight12 + weight22
                weight11 /= totweight*nlam
                weight12 /= totweight*nlam
                weight21 /= totweight*nlam
                weight22 /= totweight*nlam

                image[iy1:iy2, ix1:ix2] += val*weight11*ndimage.map_coordinates(hires[j1, i1], [yinterp, xinterp], prefilter=False)
                image[iy1:iy2, ix1:ix2] += val*weight12*ndimage.map_coordinates(hires[j1, i2], [yinterp, xinterp], prefilter=False)
                image[iy1:iy2, ix1:ix2] += val*weight21*ndimage.map_coordinates(hires[j2, i1], [yinterp, xinterp], prefilter=False)
                image[iy1:iy2, ix1:ix2] += val*weight22*ndimage.map_coordinates(hires[j2, i2], [yinterp, xinterp], prefilter=False)
     
    image = image[padding:-padding, padding:-padding]
#     image *= oldsum/np.sum(image)
    return image



def Lenslets(par, imageplane, lam,lensletplane, allweights=None,kernels=None,locations=None):
    """
    Function Lenslets
    
    Creates the IFS map on a 'dense' detector array where each pixel is smaller than the
    final detector pixels by a factor par.pxperdetpix. Adds to lensletplane array to save
    memory.
    
    Parameters
    ----------
    par :   Parameters instance
            Contains all IFS parameters
    image : 2D array
            Image plane incident on lenslets.
    lam : float
            Wavelength (microns)
    lensletplane : 2D array
            Densified detector plane; the function updates this variable
    allweights : 3D array
            Cube with weights for each kernel
    kernels : 3D array
            Kernels at locations on the detector
    locations : 2D array
            Locations where the kernels are sampled
    
    """

    # select row values
    nx,ny = imageplane.shape
    rowList = np.arange(-nx//2,-nx//2+nx)
    colList = np.arange(-ny//2,-nx//2+nx)

    I = 64
    J = 35
    # loop on all lenslets; there's got to be a way to do this faster
    for i in range(nx):
        for j in range(ny):
            jcoord = colList[j]
            icoord = rowList[i]
            val = imageplane[jcoord+imageplane.shape[0]//2,icoord+imageplane.shape[0]//2]
            
            # exit early where there is no flux
            if val==0:
                continue
            
            if par.distortPISCES:
                # in this case, the lensletplane array is oversampled by a factor par.pxperdetpix
                theta = np.arctan2(jcoord,icoord)
                r = np.sqrt(icoord**2 + jcoord**2)
                x = r*np.cos(theta+par.philens)
                y = r*np.sin(theta+par.philens)
                #if i==I and j==J: print x,y
            
                # transform this coordinate including the distortion and dispersion
                factor = 1000.*par.pitch
                X = x*factor # this is now in millimeters
                Y = y*factor # this is now in millimeters
            
                # apply polynomial transform
                ytmp,xtmp = distort(Y,X,lam)
                sy = ytmp/1000.*par.pxperdetpix/par.pixsize+lensletplane.shape[0]//2
                sx = xtmp/1000.*par.pxperdetpix/par.pixsize+lensletplane.shape[1]//2
            else:
                order = 3
                dispersion = par.npixperdlam*par.R*(lam*1000.-par.FWHMlam)/par.FWHMlam
                ### NOTE THE NEGATIVE SIGN TO PHILENS
                coef = initcoef(order, scale=par.pitch/par.pixsize, phi=-par.philens, x0=0, y0=dispersion)
                sy, sx = transform(i-nx//2, j-nx//2, order, coef)
                sx+=par.npix//2
                sy+=par.npix//2
                
            
            if not par.gaussian:
                # put the kernel in the correct spot with the correct weight
                kx,ky = kernels[0].shape
                if sx>kx//2 and sx<lensletplane.shape[0]-kx//2 \
                    and sy>ky//2 and sy<lensletplane.shape[1]-ky//2:
                    isx = int(sx)
                    isy = int(sy)
                
                    for k in range(len(locations)):
                        wx = int(isx/lensletplane.shape[0]*allweights[:,:,k].shape[0])
                        wy = int(isy/lensletplane.shape[1]*allweights[:,:,k].shape[1])
                        weight = allweights[wx,wy,k]
                        if weight ==0:
                            continue
                        xlow = isy-ky//2
                        xhigh = xlow+ky
                        ylow = isx-kx//2
                        yhigh = ylow+kx
                        lensletplane[xlow:xhigh,ylow:yhigh]+=val*weight*kernels[k]
            else:
                size = int(3*par.pitch/par.pixsize)
                if sx>size//2 and sx<lensletplane.shape[0]-size//2 \
                    and sy>size//2 and sy<lensletplane.shape[1]-size//2:
                    x = np.arange(size)-size//2 
                    y = np.arange(size)-size//2 
                    _x, _y = np.meshgrid(x, y)
                    isx = int(sx)
                    isy = int(sy)
                    rsx = sx-isx
                    rsy = sy-isy
                    sig = par.FWHM/2.35
                    psflet = np.exp(-((_x- rsx)**2+(_y- rsy)**2)/(2*(sig*lam*1000/par.FWHMlam)**2))
#                     sigma = (sig*lam*1000/par.FWHMlam)
#                     psflet = (erf((_x - rsx + 0.5) / (np.sqrt(2) * sigma)) - \
#                         erf((_x - rsx - 0.5) / (np.sqrt(2) * sigma))) * \
#                         (erf((_y - rsy + 0.5) / (np.sqrt(2) * sigma)) - \
#                         erf((_y - rsy - 0.5) / (np.sqrt(2) * sigma)))
                    psflet /= np.sum(psflet)
                    xlow = isy-size//2
                    xhigh = xlow+size
                    ylow = isx-size//2
                    yhigh = ylow+size
                    lensletplane[xlow:xhigh,ylow:yhigh]+=val*psflet

    