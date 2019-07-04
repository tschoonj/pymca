#/*##########################################################################
#
# The PyMca X-Ray Fluorescence Toolkit
#
# Copyright (c) 2019 European Synchrotron Radiation Facility
#
# This file is part of the PyMca X-ray Fluorescence Toolkit developed at
# the ESRF by the Software group.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
#############################################################################*/
__author__ = "V. Armando Sole - ESRF Data Analysis"
__contact__ = "sole@esrf.fr"
__license__ = "MIT"
__copyright__ = "European Synchrotron Radiation Facility, Grenoble, France"
import unittest
import os
import sys
import numpy
import gc
import shutil

DEBUG = 0

class testROIBatch(unittest.TestCase):
    def setUp(self):
        """
        Get the data directory
        """
        try:
            from PyMca5.PyMcaCore import StackROIBatch
            self._importSuccess = True
        except:
            self._importSuccess = False

    def testImport(self):
        self.assertTrue(self._importSuccess,
                        'Unsuccessful PyMca5.PyMcaCore.StackROIBatch import')

    def testCalculation(self):
        from PyMca5.PyMcaCore.StackROIBatch import StackROIBatch
        x = numpy.arange(2000.) / 2.
        y = 2*x + 200 * numpy.exp(-0.5*(x-500)**2)
        y.shape = 1, 1, -1

        config = {}
        config["ROI"] = {}
        config["ROI"]["roilist"] = ["roi1", "roi2", "roi3"]
        config["ROI"]["roidict"] = {}
        config["ROI"]["roidict"]["roi1"] = {}
        config["ROI"]["roidict"]["roi1"]["from"] = 10.01
        config["ROI"]["roidict"]["roi1"]["to"] = 20.01
        config["ROI"]["roidict"]["roi1"]["type"] = "Channel"
        config["ROI"]["roidict"]["roi2"] = {}
        config["ROI"]["roidict"]["roi2"]["from"] = 400.01
        config["ROI"]["roidict"]["roi2"]["to"] = 600.01
        config["ROI"]["roidict"]["roi2"]["type"] = "Channel"
        config["ROI"]["roidict"]["roi3"] = {}
        config["ROI"]["roidict"]["roi3"]["from"] = 700.01
        config["ROI"]["roidict"]["roi3"]["to"] = 800.01
        config["ROI"]["roidict"]["roi3"]["type"] = "Channel"

        instance = StackROIBatch()
        xAtMinMax = True
        outputDict = instance.batchROIMultipleSpectra(x=x,
                                                      y=y,
                                                      configuration=config,
                                                      xAtMinMax=xAtMinMax,
                                                      net=True)
        images = outputDict["images"]
        names = outputDict["names"]

        # target values
        xproc = x
        yproc = y[0, 0, :]
        for roi in config["ROI"]["roidict"]:
            toData = config["ROI"]["roidict"][roi]["to"]
            fromData = config["ROI"]["roidict"][roi]["from"]
            idx = numpy.nonzero((fromData <= xproc) & (xproc <= toData))[0]
            if len(idx):
                xw = xproc[idx]
                yw = yproc[idx]
                rawCounts = yw.sum(dtype=numpy.float)
                deltaX = xw[-1] - xw[0]
                deltaY = yw[-1] - yw[0]
                if abs(deltaX) > 0.0:
                    slope = (deltaY/deltaX)
                    background = yw[0] + slope * (xw - xw[0])
                    netCounts = rawCounts -\
                                background.sum(dtype=numpy.float)
                else:
                    netCounts = 0.0
            else:
                rawCounts = 0.0
                netCounts = 0.0
            config["ROI"]["roidict"][roi]["rawcounts"] = rawCounts
            config["ROI"]["roidict"][roi]["netcounts"] = netCounts
            rawName = "ROI " + roi + ""
            netName = "ROI " + roi + " Net"
            imageRaw = images[names.index(rawName)]
            imageNet = images[names.index(netName)]
            if (imageRaw[0, 0] != rawCounts) or \
               (imageNet[0, 0] != netCounts):
                print("ROI = ", roi)
                print("rawCounts = ", rawCounts)
                print("imageRawCounts = ", imageRaw[0, 0])
                print("netCounts = ", netCounts)
                print("imageNetCounts = ", imageNet[0, 0])

            self.assertTrue(imageRaw[0, 0] == rawCounts,
                            "Incorrect calculation for raw roi %s" % roi)
            self.assertTrue(imageNet[0, 0] == netCounts,
                            "Incorrect calculation for net roi %s delta = %f" % \
                            (roi, imageNet[0, 0] - netCounts))

            xAtMinName =  "ROI "+ roi + " Channel at Min."
            xAtMaxName =  "ROI "+ roi + " Channel at Max."
            if xAtMinMax:
                self.assertTrue(xAtMinName in names,
                                "xAtMin not calculated for roi %s" % roi)
                self.assertTrue(xAtMaxName in names,
                                "xAtMax not calculated for roi %s" % roi)

                imageMin = images[names.index(xAtMinName)]
                imageMax = images[names.index(xAtMaxName)]
                if roi == "roi2":
                    self.assertTrue(imageMax[0, 0] == 500,
                                "Max expected at 500 got %f" % imageMax[0, 0])
            else:
                self.assertTrue(xAtMinName not in names,
                                "xAtMin calculated for roi %s" % roi)
                self.assertTrue(xAtMaxName not in names,
                                "xAtMax calculated for roi %s" % roi)


    def testCalculationReversedX(self):
        from PyMca5.PyMcaCore.StackROIBatch import StackROIBatch
        x = numpy.arange(2000.) / 2 
        y = x + 200.0 * numpy.exp(-0.5*(x-500)**2)
        y.shape = 1, 1, -1
        x = -x

        config = {}
        config["ROI"] = {}
        config["ROI"]["roilist"] = ["roi1", "roi2", "roi3"]
        config["ROI"]["roidict"] = {}
        config["ROI"]["roidict"]["roi1"] = {}
        config["ROI"]["roidict"]["roi1"]["to"] = -10.01
        config["ROI"]["roidict"]["roi1"]["from"] = -20.01
        config["ROI"]["roidict"]["roi1"]["type"] = "Channel"
        config["ROI"]["roidict"]["roi2"] = {}
        config["ROI"]["roidict"]["roi2"]["to"] = -400.01
        config["ROI"]["roidict"]["roi2"]["from"] = -600.01
        config["ROI"]["roidict"]["roi2"]["type"] = "Channel"
        config["ROI"]["roidict"]["roi3"] = {}
        config["ROI"]["roidict"]["roi3"]["to"] = -700.01
        config["ROI"]["roidict"]["roi3"]["from"] = -800.01
        config["ROI"]["roidict"]["roi3"]["type"] = "Channel"

        instance = StackROIBatch()
        xAtMinMax = True
        outputDict = instance.batchROIMultipleSpectra(x=x,
                                                      y=y,
                                                      configuration=config,
                                                      xAtMinMax=xAtMinMax,
                                                      net=True)
        images = outputDict["images"]
        names = outputDict["names"]

        # target values
        xproc = x
        yproc = y[0, 0, :]
        for roi in config["ROI"]["roidict"]:
            toData = config["ROI"]["roidict"][roi]["to"]
            fromData = config["ROI"]["roidict"][roi]["from"]
            idx = numpy.nonzero((fromData <= xproc) & (xproc <= toData))[0]
            if len(idx):
                    xw = xproc[idx]
                    yw = yproc[idx]
                    rawCounts = yw.sum(dtype=numpy.float)
                    deltaX = xw[-1] - xw[0]
                    deltaY = yw[-1] - yw[0]
                    if abs(deltaX) > 0.0:
                        slope = (deltaY/deltaX)
                        background = yw[0] + slope * (xw - xw[0])
                        netCounts = rawCounts -\
                                    background.sum(dtype=numpy.float)
                    else:
                        netCounts = 0.0
            else:
                rawCounts = 0.0
                netCounts = 0.0
            config["ROI"]["roidict"][roi]["rawcounts"] = rawCounts
            config["ROI"]["roidict"][roi]["netcounts"] = netCounts
            rawName = "ROI " + roi + ""
            netName = "ROI " + roi + " Net"
            imageRaw = images[names.index(rawName)]
            imageNet = images[names.index(netName)]
            if (imageRaw[0, 0] != rawCounts) or \
               (imageNet[0, 0] != netCounts):
                print("ROI = ", roi)
                print("rawCounts = ", rawCounts)
                print("imageRawCounts = ", imageRaw[0, 0])
                print("netCounts = ", netCounts)
                print("imageNetCounts = ", imageNet[0, 0])

            self.assertTrue(imageRaw[0, 0] > -1.0e-10,
                    "Expected positive value for raw roi %s got %f" % \
                            (roi, imageRaw[0, 0]))
            self.assertTrue(imageNet[0, 0] > -1.0e-10,
                    "Expected positive value for net roi %s got %f" % \
                            (roi, imageNet[0, 0]))
            self.assertTrue(abs(imageRaw[0, 0] - rawCounts) < 1.0e-8,
                            "Incorrect calculation for raw roi %s" % roi)
            self.assertTrue(abs(imageNet[0, 0] - netCounts) < 1.0e-8,
                            "Incorrect calculation for net roi %s delta = %f" % \
                            (roi, imageNet[0, 0] - netCounts))
            xAtMinName =  "ROI "+ roi + " Channel at Min."
            xAtMaxName =  "ROI "+ roi + " Channel at Max."
            if xAtMinMax:
                self.assertTrue(xAtMinName in names,
                                "xAtMin not calculated for roi %s" % roi)
                self.assertTrue(xAtMaxName in names,
                                "xAtMax not calculated for roi %s" % roi)

                imageMin = images[names.index(xAtMinName)]
                imageMax = images[names.index(xAtMaxName)]
                if roi == "roi2":
                    self.assertTrue(imageMax[0, 0] == -500,
                                "Max expected at -500 got %f" % imageMax[0, 0])
            else:
                self.assertTrue(xAtMinName not in names,
                                "xAtMin calculated for roi %s" % roi)
                self.assertTrue(xAtMaxName not in names,
                                "xAtMax calculated for roi %s" % roi)


def getSuite(auto=True):
    testSuite = unittest.TestSuite()
    if auto:
        testSuite.addTest(unittest.TestLoader().loadTestsFromTestCase( \
                                    testROIBatch))
    else:
        # use a predefined order
        testSuite.addTest(testROIBatch("testImport"))
        testSuite.addTest(testROIBatch("testCalculation"))
        testSuite.addTest(testROIBatch("testCalculationReversedX"))
    return testSuite

def test(auto=False):
    return unittest.TextTestRunner(verbosity=2).run(getSuite(auto=auto))

if __name__ == '__main__':
    if len(sys.argv) > 1:
        auto = False
    else:
        auto = True
    result = test(auto)
    sys.exit(not result.wasSuccessful())