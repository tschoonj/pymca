#/*##########################################################################
# Copyright (C) 2004-2014 European Synchrotron Radiation Facility
#
# This file is part of the PyMca X-ray Fluorescence Toolkit developed at
# the ESRF by the Software group.
#
# This toolkit is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# PyMca is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# PyMca; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# PyMca follows the dual licensing model of Riverbank's PyQt and cannot be
# used as a free plugin for a non-free program.
#
# Please contact the ESRF industrial unit (industry@esrf.fr) if this license
# is a problem for you.
#############################################################################*/
__author__="V.A. Sole - ESRF Sofware Group"
import sys
import os
import numpy
import time
import copy
import tempfile
import shutil
import traceback

from PyMca5.PyMcaGui import PyMcaQt as qt
if hasattr(qt, "QString"):
    QString = qt.QString
else:
    QString = qt.safe_str

QTVERSION = qt.qVersion()

from PyMca5.PyMcaGui import QPyMcaMatplotlibSave1D
MATPLOTLIB = True
#force understanding of utf-8 encoding
#otherways it cannot generate svg output
try:
    import encodings.utf_8
except:
    #not a big problem
    pass

from PyMca5.PyMcaPhysics.xrf import ClassMcaTheory
from . import FitParam
from . import McaAdvancedTable
from . import QtMcaAdvancedFitReport
from . import ConcentrationsWidget
from PyMca5.PyMcaPhysics.xrf import ConcentrationsTool
from PyMca5.PyMcaGui import PlotWindow
from PyMca5.PyMcaGui import PyMca_Icons
IconDict = PyMca_Icons.IconDict
from . import McaCalWidget
from . import PeakIdentifier
from PyMca5.PyMcaGui import SubprocessLogWidget
from . import ElementsInfo
Elements = ElementsInfo.Elements
#import McaROIWidget
from PyMca5.PyMcaGui import PyMcaPrintPreview
from PyMca5.PyMcaCore import PyMcaDirs
from PyMca5.PyMcaIO import ConfigDict
DEBUG = 0
if DEBUG:
    print("############################################")
    print("#    McaAdvancedFit is in DEBUG mode %s     #" % DEBUG)
    print("############################################")
print("XRFMC TO be imported")
XRFMC_FLAG = False
try:
    from PyMca.XRFMC import XRFMCHelper
    XRFMC_FLAG = True
except ImportError:
    if DEBUG:
        print("Cannot import XRFMCHelper module")
        raise
USE_BOLD_FONT = True

class McaAdvancedFit(qt.QWidget):
    """
    This class inherits QWidget.

    It provides all the functionality required to perform an interactive fit
    and to generate a configuration file.

    It is the simplest way to embed PyMca's fitting functionality into other
    PyQt application.

    It can be used from the interactive prompt of ipython provided ipython is
    started with the -q4thread flag.

    **Usage**

    >>> from PyMca5 import McaAdvancedFit
    >>> w = McaAdvancedFit.McaAdvancedFit()
    >>> w.setData(x=x, y=y) # x is your channel array and y the counts array
    >>> w.show()
    
    """
    sigMcaAdvancedFitSignal = qt.pyqtSignal(object)
    
    def __init__(self, parent=None, name="PyMca - McaAdvancedFit",fl=0,
                 sections=None, top=True, margin=11, spacing=6):
        qt.QWidget.__init__(self, parent)
        self.setWindowTitle(name)
        self.setWindowIcon(qt.QIcon(qt.QPixmap(IconDict['gioconda16'])))
        self.lastInputDir = None
        self.configDialog = None
        self.matplotlibDialog = None
        self.mainLayout = qt.QVBoxLayout(self)
        self.mainLayout.setContentsMargins(margin, margin, margin, margin)
        self.mainLayout.setSpacing(0)
        if sections is None:
            sections=["TABLE"]
        self.headerLabel = qt.QLabel(self)
        self.mainLayout.addWidget(self.headerLabel)

        self.headerLabel.setAlignment(qt.Qt.AlignHCenter)
        font = self.font()
        font.setBold(USE_BOLD_FONT)
        self.headerLabel.setFont(font)
        self.setHeader('Fit of XXXXXXXXXX from Channel XXXXX to XXXX')
        self.top = Top(self)
        self.mainLayout.addWidget(self.top)
        self.sthread = None
        self.elementsInfo = None
        self.identifier   = None
        self.logWidget = None
        if False and len(sections) == 1:
            w = self
            self.mcatable  = McaAdvancedTable.McaTable(w)
            self.concentrationsWidget = None
        else:
            self.mainTab = qt.QTabWidget(self)
            self.mainLayout.addWidget(self.mainTab)
            #graph
            self.tabGraph  = qt.QWidget()
            tabGraphLayout = qt.QVBoxLayout(self.tabGraph)
            tabGraphLayout.setContentsMargins(margin, margin, margin, margin)
            tabGraphLayout.setSpacing(spacing)
            #self.graphToolbar  = qt.QHBox(self.tabGraph)
            self.graphWindow = McaGraphWindow(self.tabGraph)
            tabGraphLayout.addWidget(self.graphWindow)
            self.graph = self.graphWindow
            self.graph.setGraphXLabel('Channel')
            self.graph.setGraphYLabel('Counts')
            self.mainTab.addTab(self.tabGraph,"GRAPH")
            self.graphWindow.sigPlotSignal.connect(self._mcaGraphSignalSlot)
            #table
            self.tabMca  = qt.QWidget()
            tabMcaLayout = qt.QVBoxLayout(self.tabMca)
            tabMcaLayout.setContentsMargins(margin, margin, margin, margin)
            tabMcaLayout.setSpacing(spacing)
            w = self.tabMca
            line = Line(w, info="TABLE")
            tabMcaLayout.addWidget(line)

            line.setToolTip("DoubleClick toggles floating window mode")

            self.mcatable  = McaAdvancedTable.McaTable(w)
            tabMcaLayout.addWidget(self.mcatable)
            self.mainTab.addTab(w,"TABLE")
            self.connect(line,qt.SIGNAL("LineDoubleClickEvent"),
                            self._tabReparent)
            self.connect(self.mcatable,qt.SIGNAL("closed"),
                            self._mcatableClose)

            #concentrations
            self.tabConcentrations  = qt.QWidget()
            tabConcentrationsLayout = qt.QVBoxLayout(self.tabConcentrations)
            tabConcentrationsLayout.setContentsMargins(margin,
                                                       margin,
                                                       margin,
                                                       margin)
            tabConcentrationsLayout.setSpacing(0)
            line2 = Line(self.tabConcentrations, info="CONCENTRATIONS")
            self.concentrationsWidget = ConcentrationsWidget.Concentrations(self.tabConcentrations)
            tabConcentrationsLayout.addWidget(line2)
            tabConcentrationsLayout.addWidget(self.concentrationsWidget)

            self.mainTab.addTab(self.tabConcentrations,"CONCENTRATIONS")
            line2.setToolTip("DoubleClick toggles floating window mode")
            self.connect(self.concentrationsWidget,
                        qt.SIGNAL("ConcentrationsSignal"),
                        self.__configureFromConcentrations)
            self.connect(line2,qt.SIGNAL("LineDoubleClickEvent"),
                            self._tabReparent)
            self.connect(self.concentrationsWidget,qt.SIGNAL("closed"),
                            self._concentrationsWidgetClose)

            #diagnostics
            self.tabDiagnostics  = qt.QWidget()
            tabDiagnosticsLayout = qt.QVBoxLayout(self.tabDiagnostics)
            tabDiagnosticsLayout.setContentsMargins(margin, margin, margin, margin)
            tabDiagnosticsLayout.setSpacing(spacing)
            w = self.tabDiagnostics
            self.diagnosticsWidget = qt.QTextEdit(w)
            self.diagnosticsWidget.setReadOnly(1)

            tabDiagnosticsLayout.addWidget(self.diagnosticsWidget)
            self.mainTab.addTab(w,"DIAGNOSTICS")
            self.connect(self.mainTab, qt.SIGNAL('currentChanged(int)'),
                         self._tabChanged)


        self._logY       = False
        self._energyAxis = False
        self.__printmenu = qt.QMenu()
        self.__printmenu.addAction(QString("Calibrate"),     self._calibrate)
        self.__printmenu.addAction(QString("Identify Peaks"),self.__peakIdentifier)
        self.__printmenu.addAction(QString("Elements Info"), self.__elementsInfo)
        self.outdir      = None
        self.configDir   = None
        self.__lastreport= None
        self.browser     = None
        self.info        = {}
        self.__fitdone   = 0
        self._concentrationsDict = None
        self._concentrationsInfo = None
        self._xrfmcMatrixSpectra = None
        #self.graph.hide()
        #self.guiconfig = FitParam.Fitparam()
        """
        self.specfitGUI.guiconfig.MCACheckBox.setEnabled(0)
        palette = self.specfitGUI.guiconfig.MCACheckBox.palette()
        palette.setDisabled(palette.active())
        """
        ##############
        hbox=qt.QWidget(self)
        self.bottom = hbox
        hboxLayout = qt.QHBoxLayout(hbox)
        hboxLayout.setContentsMargins(0, 0, 0, 0)
        hboxLayout.setSpacing(4)
        if not top:
            self.configureButton = qt.QPushButton(hbox)
            self.configureButton.setText("Configure")
            self.toolsButton = qt.QPushButton(hbox)
            self.toolsButton.setText("Tools")
            hboxLayout.addWidget(self.configureButton)
            hboxLayout.addWidget(self.toolsButton)
        hboxLayout.addWidget(qt.HorizontalSpacer(hbox))
        self.fitButton = qt.QPushButton(hbox)
        hboxLayout.addWidget(self.fitButton)
        #font = self.fitButton.font()
        #font.setBold(True)
        #self.fitButton.setFont(font)
        self.fitButton.setText("Fit Again!")
        self.printButton = qt.QPushButton(hbox)
        hboxLayout.addWidget(self.printButton)
        self.printButton.setText("Print")
        self.htmlReportButton = qt.QPushButton(hbox)
        hboxLayout.addWidget(self.htmlReportButton)
        self.htmlReportButton.setText("HTML Report")
        self.matrixSpectrumButton = qt.QPushButton(hbox)
        hboxLayout.addWidget(self.matrixSpectrumButton)
        self.matrixSpectrumButton.setText("Matrix Spectrum")
        self.matrixXRFMCSpectrumButton = qt.QPushButton(hbox)
        self.matrixXRFMCSpectrumButton.setText("MC Matrix Spectrum")
        hboxLayout.addWidget(self.matrixXRFMCSpectrumButton)
        self.matrixXRFMCSpectrumButton.hide()
        self.peaksSpectrumButton = qt.QPushButton(hbox)
        hboxLayout.addWidget(self.peaksSpectrumButton)
        self.peaksSpectrumButton.setText("Peaks Spectrum")
        self.matrixSpectrumButton.setCheckable(1)
        self.peaksSpectrumButton.setCheckable(1)
            
        hboxLayout.addWidget(qt.HorizontalSpacer(hbox))
        self.dismissButton = qt.QPushButton(hbox)
        hboxLayout.addWidget(self.dismissButton)
        self.dismissButton.setText("Dismiss")
        hboxLayout.addWidget(qt.HorizontalSpacer(hbox))

        self.mainLayout.addWidget(hbox)
        self.printButton.setToolTip('Print Active Tab')
        self.htmlReportButton.setToolTip('Generate Browser Compatible Output\nin Chosen Directory')
        self.matrixSpectrumButton.setToolTip('Toggle Matrix Spectrum Calculation On/Off')
        self.matrixXRFMCSpectrumButton.setToolTip('Calculate Matrix Spectrum Using Monte Carlo')
        self.peaksSpectrumButton.setToolTip('Toggle Individual Peaks Spectrum Calculation On/Off')

        self.mcafit   = ClassMcaTheory.McaTheory()

        self.fitButton.clicked.connect(self.fit)
        self.printButton.clicked.connect(self.printActiveTab)
        self.htmlReportButton.clicked.connect(self.htmlReport)
        self.matrixSpectrumButton.clicked.connect(self.__toggleMatrixSpectrum)
        if self.matrixXRFMCSpectrumButton is not None:
            self.matrixXRFMCSpectrumButton.clicked.connect(self.xrfmcSpectrum)
        self.peaksSpectrumButton.clicked.connect(self.__togglePeaksSpectrum)
        self.dismissButton.clicked.connect(self.dismiss)
        self.top.configureButton.clicked.connect(self.__configure)
        self.top.printButton.clicked.connect(self.__printps)
        if top:
            self.connect(self.top,qt.SIGNAL("TopSignal"), self.__updatefromtop)
        else:
            self.top.hide()
            self.configureButton.clicked.connect(self.__configure)
            self.toolsButton.clicked.connect(self.__printps)
        self._updateTop()

    def __mainTabPatch(self, index):
        return self.mainTabLabels[index]

    def _fitdone(self):
        if self.__fitdone:
            return True
        else:
            return False

    def _submitThread(self, function, parameters, message="Please wait",
                    expandparametersdict=None):
        if expandparametersdict is None: expandparametersdict= False
        sthread = SimpleThread()
        sthread._expandParametersDict=expandparametersdict
        sthread._function = function
        sthread._kw       = parameters
        #try:
        sthread.start()
        #except:
        #    raise "ThreadError",sys.exc_info()
        msg = qt.QDialog(self, qt.Qt.FramelessWindowHint)
        msg.setModal(0)
        msg.setWindowTitle("Please Wait")
        layout = qt.QHBoxLayout(msg)
        l1 = qt.QLabel(msg)
        layout.addWidget(l1)
        l1.setFixedWidth(l1.fontMetrics().width('##'))
        l2 = qt.QLabel(msg)
        layout.addWidget(l2)
        l2.setText("%s" % message)
        l3 = qt.QLabel(msg)
        layout.addWidget(l3)
        l3.setFixedWidth(l3.fontMetrics().width('##'))
        msg.show()
        qt.qApp.processEvents()
        i = 0
        ticks = ['-','\\', "|", "/","-","\\",'|','/']
        while (sthread.isRunning()):
            i = (i+1) % 8
            l1.setText(ticks[i])
            l3.setText(" "+ticks[i])
            qt.qApp.processEvents()
            time.sleep(1)
        msg.close()
        result = sthread._result
        del sthread
        self.raise_()
        return result

    def refreshWidgets(self):
        """
        This method just forces the graphical widgets to get updated.
        It should be called if somehow you have modified the fit and/
        or concentrations parameters by other means than the graphical
        interface.
        """
        self.__configure(justupdate=True)

    def configure(self, ddict=None):
        """
        This methods configures the fitting parameters and updates the
        graphical interface.

        It returns the current configuration.
        """
        if ddict is None:
            return self.mcafit.configure(ddict)

        #configure and get the new configuration
        newConfig = self.mcafit.configure(ddict)

        #refresh the interface
        self.refreshWidgets()

        #return the current configuration
        return newConfig

    def __configure(self, justupdate=False):
        config = {}
        config.update(self.mcafit.config)
        #config['fit']['use_limit'] = 1
        if not justupdate:
            if self.configDialog is None:
                if self.__fitdone:
                    dialog = FitParam.FitParamDialog(modal=1,
                                                     fl=0,
                                                     initdir=self.configDir,
                                                     fitresult=self.dict['result'])
                else:
                    dialog = FitParam.FitParamDialog(modal=1,
                                                     fl=0,
                                                     initdir=self.configDir,
                                                     fitresult=None)
                self.connect(dialog.fitparam.peakTable,
                             qt.SIGNAL("FitPeakSelect"),
                             self.__elementclicked)
                self.configDialog = dialog
            else:
                dialog = self.configDialog
                if self.__fitdone:
                    dialog.setFitResult(self.dict['result'])
                else:
                    dialog.setFitResult(None)
            dialog.setParameters(config)
            dialog.setData(self.mcafit.xdata * 1.0,
                           self.mcafit.ydata * 1.0)

            
            #dialog.fitparam.regionCheck.setDisabled(True)
            #dialog.fitparam.minSpin.setDisabled(True)
            #dialog.fitparam.maxSpin.setDisabled(True)
            ret = dialog.exec_()
            if dialog.initDir is not None:
                self.configDir = 1 * dialog.initDir
            else:
                self.configDir = None
            if ret != qt.QDialog.Accepted:
                dialog.close()
                #del dialog
                return
            try:
                #this may crash in qt 2.3.0
                npar = dialog.getParameters()
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Error occured getting parameters:")
                msg.setInformativeText(str(sys.exc_info()[1]))
                msg.setDetailedText(traceback.format_exc())
                msg.exec_()
                return
            config.update(npar)
            dialog.close()
            #del dialog

        self.graph.clearMarkers()
        self.graph.replot()
        self.__fitdone = False
        self._concentrationsDict = None
        self._concentrationsInfo = None
        self._xrfmcMatrixSpectra = None
        if self.concentrationsWidget is not None:
            self.concentrationsWidget.concentrationsTable.setRowCount(0)
        if self.mcatable is not None:
            self.mcatable.setRowCount(0)

        #make sure newly or redefined materials are added to the
        #materials in the fit configuration
        for material in Elements.Material.keys():
            self.mcafit.config['materials'][material] =copy.deepcopy(Elements.Material[material])

        hideButton = True
        if 'xrfmc' in config:
            programFile = config['xrfmc'].get('program', None)
            if programFile is not None:
                if os.path.exists(programFile):
                    if os.path.isfile(config['xrfmc']['program']):
                        hideButton = False
        if hideButton:
            self.matrixXRFMCSpectrumButton.hide()
        else:
            self.matrixXRFMCSpectrumButton.show()

        if DEBUG:
            self.mcafit.configure(config)
        else:
            try:
                threadResult=self._submitThread(self.mcafit.configure, config,
                                 "Configuring, please wait")
                if type(threadResult) == type((1,)):
                    if len(threadResult):
                        if threadResult[0] == "Exception":
                            raise Exception(threadResult[1], threadResult[2])
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setWindowTitle("Configuration error")
                msg.setText("Error configuring fit:")
                msg.setInformativeText(str(sys.exc_info()[1]))
                msg.setDetailedText(traceback.format_exc())
                msg.exec_()
                return

        #update graph
        delcurves = []
        curveList = self.graph.getAllCurves(just_legend=True)
        for key in curveList:
            if key not in ["Data"]:
                delcurves.append(key)
        for key in delcurves:
            self.graph.removeCurve(key)

        if not justupdate:
            self.plot()


        self._updateTop()
        if self.concentrationsWidget is not None:
            try:
                qt.qApp.processEvents()
                self.concentrationsWidget.setParameters(config['concentrations'], signal=False)
            except:
                if str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == "CONCENTRATIONS":
                    self.mainTab.setCurrentIndex(0)

    def __configureFromConcentrations(self,ddict):
        config = self.concentrationsWidget.getParameters()
        self.mcafit.config['concentrations'].update(config)
        if ddict['event'] == 'updated':
            if 'concentrations' in ddict:
                self._concentrationsDict = ddict['concentrations']
                self._concentrationsInfo = None
                self._xrfmcMatrixSpectra = None

    def __elementclicked(self,ddict):
        ddict['event'] = 'McaAdvancedFitElementClicked'
        self.__showElementMarker(ddict)
        self.__anasignal(ddict)

    def __showElementMarker(self, dict):
        self.graph.clearMarkers()
        ele = dict['current']
        items = []
        if not (ele in dict):
            self.graph.replot()
            return
        for rays in dict[ele]:
            for transition in Elements.Element[ele][rays +" xrays"]:
                items.append([transition,
                              Elements.Element[ele][transition]['energy'],
                              Elements.Element[ele][transition]['rate']])

        config = self.mcafit.configure()
        xdata  = self.mcafit.xdata * 1.0
        xmin = xdata[0]
        xmax = xdata[-1]
        ymin,ymax = self.graph.getGraphYLimits()
        calib = [config['detector'] ['zero'], config['detector'] ['gain']]
        for transition,energy,rate in items:
            marker = ""
            x = (energy - calib[0])/calib[1]
            if (x < xmin) or (x > xmax):continue
            if not self._energyAxis:
                if abs(calib[1]) > 0.0000001:
                    marker=self.graph.insertXMarker(x,
                                                    label=transition,
                                                    color='orange')
            else:
                marker=self.graph.insertXMarker(energy,
                                                label=transition,
                                                color='orange')
        self.graph.replot()

    def _updateTop(self):
        config = {}
        if 0:
            config.update(self.mcafit.config['fit'])
        else:
            config['stripflag']    = self.mcafit.config['fit'].get('stripflag',0)
            config['fitfunction'] = self.mcafit.config['fit'].get('fitfunction',0)
            config['hypermetflag'] = self.mcafit.config['fit'].get('hypermetflag',1)
            config['sumflag']      = self.mcafit.config['fit'].get('sumflag',0)
            config['escapeflag']   = self.mcafit.config['fit'].get('escapeflag',0)
            config['continuum']    = self.mcafit.config['fit'].get('continuum',0)
        self.top.setParameters(config)

    def __updatefromtop(self,ndict):
        config = self.mcafit.configure()
        for key in ndict.keys():
            if DEBUG:
                keylist = ['stripflag','hypermetflag','sumflag','escapeflag',
                           'fitfunction', 'continuum']
                if key not in keylist:
                    print("UNKNOWN key ",key)
            config['fit'][key] = ndict[key]
        self.__fitdone = False
        #erase table
        if self.mcatable is not None:
            self.mcatable.setRowCount(0)
        #erase concentrations
        if self.concentrationsWidget is not None:
            self.concentrationsWidget.concentrationsTable.setRowCount(0)
        #update graph
        curveList = self.graph.getAllCurves(just_legend=True)
        delcurves = []
        for key in curveList:
            if key not in ["Data"]:
                delcurves.append(key)
        for key in delcurves:
            self.graph.removeCurve(key)
        self.plot()
        
        if DEBUG:
            self.mcafit.configure(config)
        else:
            threadResult=self._submitThread(self.mcafit.configure, config,
                             "Configuring, please wait")
            if type(threadResult) == type((1,)):
                if len(threadResult):
                    if threadResult[0] == "Exception":
                        raise Exception(threadResult[1], threadResult[2])

    def _tabChanged(self, value):
        if DEBUG:
            print("_tabChanged(self, value) called")
        if str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == "CONCENTRATIONS":
            self.printButton.setEnabled(False)
            w = self.concentrationsWidget
            if w.parent() is None:
                if w.isHidden():
                    w.show()
                w.raise_()
                self.printButton.setEnabled(True)
                #do not calculate again. It should be already updated
                return
            if DEBUG:
                self.concentrations()
                self.printButton.setEnabled(True)
            else:
                try:
                    self.concentrations()
                    self.printButton.setEnabled(True)
                except:
                    #print "try to set"
                    self.printButton.setEnabled(False)
                    msg = qt.QMessageBox(self)
                    msg.setIcon(qt.QMessageBox.Critical)
                    msg.setText("Concentrations error: %s" % sys.exc_info()[1])
                    msg.exec_()
                    self.mainTab.setCurrentIndex(0)
        elif str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == "TABLE":
            self.printButton.setEnabled(True)
            w = self.mcatable
            if w.parent() is None:
                if w.isHidden():
                    w.show()
                w.raise_()
        elif str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == "DIAGNOSTICS":
            self.printButton.setEnabled(False)
            self.diagnostics()
        else:
            self.printButton.setEnabled(True)

    def _concentrationsWidgetClose(self, ddict):
        ddict['info'] = "CONCENTRATIONS"
        self._tabReparent(ddict)

    def _mcatableClose(self, ddict):
        ddict['info'] = "TABLE"
        self._tabReparent(ddict)

    def _tabReparent(self, ddict):
        if ddict['info'] == "CONCENTRATIONS":
            w = self.concentrationsWidget
            parent = self.tabConcentrations
        elif ddict['info'] == "TABLE":
            w = self.mcatable
            parent = self.tabMca
        if w.parent() is not None:
            parent.layout().removeWidget(w)
            w.setParent(None)
            w.show()
        else:
            w.setParent(parent)
            parent.layout().addWidget(w)

    def _calibrate(self):
        config = self.mcafit.configure()
        x = self.mcafit.xdata0[:]
        y = self.mcafit.ydata0[:]
        legend = "Calibration for " + qt.safe_str(self.headerLabel.text())
        ndict={}
        ndict[legend] = {'A':config['detector']['zero'],
               'B':config['detector']['gain'],
               'C': 0.0}
        caldialog = McaCalWidget.McaCalWidget(legend=legend,
                                                     x=x,
                                                     y=y,
                                                     modal=1,
                                                     caldict=ndict,
                                                     fl=0)
        caldialog.calpar.orderbox.setEnabled(0)
        caldialog.calpar.CText.setEnabled(0)
        caldialog.calpar.savebox.setEnabled(0)
        ret = caldialog.exec_()
        if ret == qt.QDialog.Accepted:
            ddict = caldialog.getDict()
            config['detector']['zero'] = ddict[legend]['A']
            config['detector']['gain'] = ddict[legend]['B']
            #self.mcafit.configure(config)
            self.mcafit.config['detector']['zero'] = 1. * ddict[legend]['A']
            self.mcafit.config['detector']['gain'] = 1. * ddict[legend]['B']
            self.__fitdone = 0
            self.plot()
        del caldialog

    def __elementsInfo(self):
        if self.elementsInfo is None:
            self.elementsInfo = ElementsInfo.ElementsInfo(None, "Elements Info")
        if self.elementsInfo.isHidden():
           self.elementsInfo.show()
        self.elementsInfo.raise_()

    def __peakIdentifier(self, energy = None):
        if energy is None:energy = 5.9
        if self.identifier is None:
            self.identifier=PeakIdentifier.PeakIdentifier(energy=energy,
                                                          threshold=0.040,
                                                          useviewer=1)
            self.identifier.myslot()
        self.identifier.setEnergy(energy)
        if self.identifier.isHidden():
            self.identifier.show()
        self.identifier.raise_()

    def printActiveTab(self):
        txt = str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() 
        if txt == "GRAPH":
            self.graph.printps()
        elif txt == "TABLE":
            self.printps(True)
        elif txt == "CONCENTRATIONS":
            self.printConcentrations(True)
        elif txt == "DIAGNOSTICS":
            pass
        else:
            pass

    def diagnostics(self):
        if not self.__fitdone:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            text = "Sorry. You need to perform a fit first.\n"
            msg.setText(text)
            msg.exec_()
            if str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == "DIAGNOSTICS":
                self.mainTab.setCurrentIndex(0)
            return
        fitresult = self.dict
        x = fitresult['result']['xdata']
        energy = fitresult['result']['energy']
        y = fitresult['result']['ydata']
        yfit = fitresult['result']['yfit']
        param = fitresult['result']['fittedpar']
        i    = fitresult['result']['parameters'].index('Noise')
        noise= param[i] * param[i]
        i    = fitresult['result']['parameters'].index('Fano')
        fano = param[i] * 2.3548*2.3548*0.00385
        meanfwhm = numpy.sqrt(noise + 0.5 * (energy[0] + energy[-1]) * fano)
        i = fitresult['result']['parameters'].index('Gain')
        gain = fitresult['result']['fittedpar'][i]
        meanfwhm = int(meanfwhm/gain) + 1
        missed =  self.mcafit.detectMissingPeaks(y, yfit, meanfwhm)
        hcolor = 'white'
        finalcolor = 'white'
        text=""
        if len(missed):
            text+="<br><b><font color=blue size=4>Possibly Missing or Underestimated Peaks</font></b>"
            text+="<nobr><table><tr>"
            text+='<td align="right" bgcolor="%s"><b>' % hcolor
            text+='Channel'
            text+="</b></td>"
            text+='<td align="right" bgcolor="%s"><b>' % hcolor
            text+='Energy'
            text+="</b></td>"
            text+="</tr>"
            text+="<tr>"
            for peak in missed:
                text+="<tr>"
                text+='<td align="right" bgcolor="%s">' % finalcolor
                text+="<b><font size=3>%d </font></b>"  % x[int(peak)]
                text+="</td>"
                text+='<td align="right" bgcolor="%s">' % finalcolor
                text+="<b><font size=3>%.3f </font></b>"  % energy[int(peak)]
                text+="</td>"
            text+="</tr>"
            text+="</table>"
        missed =  self.mcafit.detectMissingPeaks(yfit, y, meanfwhm)
        if len(missed):
            text+="<br><b><font color=blue size=4>Possibly Overestimated Peaks</font></b>"
            text+="<nobr><table><tr>"
            text+='<td align="right" bgcolor="%s"><b>' % hcolor
            text+='Channel'
            text+="</b></td>"
            text+='<td align="right" bgcolor="%s"><b>' % hcolor
            text+='Energy'
            text+="</b></td>"
            text+="</tr>"
            text+="<tr>"
            for peak in missed:
                text+="<tr>"
                text+='<td align="right" bgcolor="%s">' % finalcolor
                text+="<b><font size=3>%d </font></b>"  % x[int(peak)]
                text+="</td>"
                text+='<td align="right" bgcolor="%s">' % finalcolor
                text+="<b><font size=3>%.3f </font></b>"  % energy[int(peak)]
                text+="</td>"
            text+="</tr>"
            text+="</table>"
        self.diagnosticsWidget.clear()
        self.diagnosticsWidget.insertHtml(text)

    def concentrations(self):
        self._concentrationsDict = None
        self._concentrationsInfo = None
        self._xrfmcMatrixSpectra = None
        if not self.__fitdone:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            text = "Sorry, You need to perform a fit first.\n"
            msg.setText(text)
            msg.exec_()
            if str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == "CONCENTRATIONS":
                self.mainTab.setCurrentIndex(0)
            return
        fitresult = self.dict
        if False:
            #from the fit, it misses any update from concentrations
            config = fitresult['result']['config']
        else:
            #from current, it should be up to date
            config = self.mcafit.configure()
        #tool = ConcentrationsWidget.Concentrations(fl=qt.Qt.WDestructiveClose)
        if self.concentrationsWidget is None:
           self.concentrationsWidget = ConcentrationsWidget.Concentrations()
           self.connect(self.concentrationsWidget,
                        qt.SIGNAL("ConcentrationsSignal"),
                        self.__configureFromConcentrations)
        tool = self.concentrationsWidget
        #this forces update
        tool.getParameters()
        ddict = {}
        ddict.update(config['concentrations'])
        tool.setParameters(ddict, signal=False)
        if DEBUG:
            ddict, info = tool.processFitResult(config=ddict,fitresult=fitresult,
                                                elementsfrommatrix=False,
                                                fluorates = self.mcafit._fluoRates,
                                                addinfo=True)
        else:
            try:
                ddict, info = tool.processFitResult(config=ddict,fitresult=fitresult,
                                                    elementsfrommatrix=False,
                                                    fluorates = self.mcafit._fluoRates,
                                                    addinfo=True)
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Error processing fit result: %s" % (sys.exc_info()[1]))
                msg.exec_()
                if str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == 'CONCENTRATIONS':
                    self.mainTab.setCurrentIndex(0)
                return
        self._concentrationsDict = ddict
        self._concentrationsInfo = info
        tool.show()
        tool.setFocus()
        tool.raise_()

    def __toggleMatrixSpectrum(self):
        if self.matrixSpectrumButton.isChecked():
            self.matrixSpectrum()
            self.plot()
        else:
            if "Matrix" in self.graph.getAllCurves(just_legend=True):
                self.graph.removeCurve("Matrix")
                self.plot()

    def __togglePeaksSpectrum(self):
        if self.peaksSpectrumButton.isChecked():
            self.peaksSpectrum()
        else:
            self.__clearPeaksSpectrum()
        self.plot()
        
    def __clearPeaksSpectrum(self):
        delcurves = []
        for key in self.graph.getAllCurves(just_legend=True):
            if key not in ["Data", "Fit", "Continuum", "Pile-up", "Matrix"]:
                if key.startswith('MC Matrix'):
                    if self._xrfmcMatrixSpectra in [None, []]:
                        delcurves.append(key)
                else:
                    delcurves.append(key)
        for key in delcurves:
            self.graph.removeCurve(key, replot=False)
        

    def matrixSpectrum(self):
        if not self.__fitdone:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            text = "Sorry, for the time being you need to perform a fit first\n"
            text+= "in order to calculate the spectrum derived from the matrix.\n"
            text+= "Background and detector parameters are taken from last fit"
            msg.setText(text)
            msg.exec_()
            return
        #fitresult = self.dict['result']
        fitresult = self.dict
        config = self.mcafit.configure()
        self._concentrationsInfo = None
        tool   = ConcentrationsTool.ConcentrationsTool()
        #this forces update
        tool.configure()
        ddict = {}
        ddict.update(config['concentrations'])
        tool.configure(ddict)
        if DEBUG:
            ddict, info = tool.processFitResult(fitresult=fitresult,
                                         elementsfrommatrix=True,
                                         addinfo=True)
        else:
            try:
                threadResult = self._submitThread(tool.processFitResult,
                                   {'fitresult':fitresult,
                                    'elementsfrommatrix':True,
                                    'addinfo':True},
                                   "Calculating Matrix Spectrum",
                                   True)
                if type(threadResult) == type((1,)):
                    if len(threadResult):
                        if threadResult[0] == "Exception":
                            raise Exception(threadResult[1], threadResult[2])
                ddict, info = threadResult
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Error: %s" % (sys.exc_info()[1]))
                msg.exec_()
                return
        self._concentrationsInfo = info
        groupsList = fitresult['result']['groups']

        if type(groupsList) != type([]):
            groupsList = [groupsList]
        areas = []
        for group in groupsList:
            item = group.split()
            element = item[0]
            if len(element) >2:
                areas.append(0.0)
            else:
                # transitions = item[1] + " xrays"
                areas.append(ddict['area'][group])

        nglobal    = len(fitresult['result']['parameters']) - len(groupsList)
        parameters = []
        for i in range(len(fitresult['result']['parameters'])):
            if i < nglobal:
                parameters.append(fitresult['result']['fittedpar'][i])
            else:
                parameters.append(areas[i-nglobal])

        xmatrix = fitresult['result']['xdata']
        ymatrix = self.mcafit.mcatheory(parameters,xmatrix)
        ymatrix.shape =  [len(ymatrix),1]
        ddict=copy.deepcopy(self.dict)
        ddict['event'] = "McaAdvancedFitMatrixFinished"
        if self.mcafit.STRIP:
            ddict['result']['ymatrix']  = ymatrix + self.mcafit.zz
        else:
            ddict['result']['ymatrix']  = ymatrix
        ddict['result']['ymatrix'].shape  = (len(ddict['result']['ymatrix']),)
        ddict['result']['continuum'].shape  = (len(ddict['result']['ymatrix']),)
        if self.matrixSpectrumButton.isChecked():
            self.dict['result']['ymatrix']= ddict['result']['ymatrix'] * 1.0
        """
        if self.graph is not None:
            if self._logY:
                logfilter = 1
            else:
                logfilter = 0
            if self._energyAxis:
                xdata = dict['result']['energy'][:]
            else:
                xdata = dict['result']['xdata'][:]
            self.graph.newCurve("Matrix",xdata,dict['result']['ymatrix'],logfilter=logfilter)
        """
        try:
            self.__anasignal(ddict)
        except:
            print("Error generating matrix output. ")
            print("Try to perform your fit again.  ")
            print(sys.exc_info())
            print("If error persists, please report this error.")
            print("ymatrix shape = ", ddict['result']['ymatrix'].shape)
            print("xmatrix shape = ", xmatrix.shape)
            print("continuum shape = ", ddict['result']['continuum'].shape)
            print("zz      shape = ", self.mcafit.zz.shape)

    def xrfmcSpectrum(self):
        if not self.__fitdone:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            text = "Sorry, current implementation requires you to perform a fit first\n"
            msg.setText(text)
            msg.exec_()
            return
        fitresult = self.dict
        self._xrfmcMatrixSpectra = None
        if self._concentrationsInfo is None:
            # concentrations have to be calculated too
            self.concentrations()

        # force the Monte Carlo to work on fundamental parameters mode
        ddict = copy.deepcopy(self.dict)
        ddict['result']['config']['concentrations']['usematrix'] = 0
        ddict['result']['config']['concentrations']['flux'] = self._concentrationsInfo['Flux']
        ddict['result']['config']['concentrations']['time'] = self._concentrationsInfo['Time']

        if hasattr(self, "__tmpMatrixSpectrumDir"):
            if self.__tmpMatrixSpectrumDir is not None:
                self.removeDirectory(self.__tmpMatrixSpectrumDir)

        self.__tmpMatrixSpectrumDir = tempfile.mkdtemp(prefix="pymcaTmp")
        nfile = ConfigDict.ConfigDict()
        nfile.update(ddict)
        #the Monte Carlo expects this at top level
        nfile['xrfmc'] = ddict['result']['config']['xrfmc']
        newFile = os.path.join(self.__tmpMatrixSpectrumDir, "pymcaTmpFitFile.fit")
        if os.path.exists(newFile):
            # this should never happen
            os.remove(newFile)
        nfile.write(newFile)
        nfile = None
        fileNamesDict = XRFMCHelper.getOutputFileNames(newFile,
                                                       outputDir=self.__tmpMatrixSpectrumDir)
        if newFile != fileNamesDict['fit']:
            removeDirectory(self.__tmpMatrixSpectrumDir)
            raise ValueError("Inconsistent internal behaviour!")

        self._xrfmcFileNamesDict = fileNamesDict
        xrfmcProgram = ddict['result']['config']['xrfmc']['program']

        scriptName = fileNamesDict['script']
        scriptFile = XRFMCHelper.getScriptFile(xrfmcProgram, name=scriptName)
        csvName = fileNamesDict['csv']
        speName = fileNamesDict['spe']
        xmsoName = fileNamesDict['xmso']
        # basic parameters
        args = [scriptFile,
               "--verbose",
               "--spe-file=%s" % speName,
               "--csv-file=%s" % csvName,
               #"--enable-roi-normalization",
               #"--disable-roi-normalization", #default
               #"--enable-pile-up"
               #"--disable-pile-up" #default
               #"--enable-poisson",
               #"--disable-poisson", #default no noise
               #"--set-threads=2", #overwrite default maximum
               newFile,
               xmsoName]

        # additionalParameters
        simulationParameters = ["--enable-single-run"]
        #simulationParameters = ["--enable-single-run",
        #                        "--set-threads=2"]
        i = 0
        for parameter in simulationParameters:
            i += 1             
            args.insert(1, parameter)

        # show the command on the log widget
        text = "%s" % scriptFile 
        for arg in args[1:]:
            text += " %s" % arg
        if self.logWidget is None:
            self.logWidget = SubprocessLogWidget.SubprocessLogWidget()
            self.logWidget.setMinimumWidth(400)
            self.logWidget.sigSubprocessLogWidgetSignal.connect(\
                self._xrfmcSubprocessSlot)
        self.logWidget.clear()
        self.logWidget.show()
        self.logWidget.raise_()
        self.logWidget.append(text)
        self.logWidget.start(args=args)

    def removeDirectory(self, dirName):
        if os.path.exists(dirName):
            if os.path.isdir(dirName):
                shutil.rmtree(dirName)

    def _xrfmcSubprocessSlot(self, ddict):
        if ddict['event'] == "ProcessFinished":
            returnCode = ddict['code']
            msg = qt.QMessageBox(self)
            msg.setWindowTitle("Simulation finished")
            if returnCode != 0:
                msg = qt.QMessageBox(self)
                msg.setWindowTitle("Simulation Error")
                msg.setIcon(qt.QMessageBox.Critical)
                text = "Simulation finished with error code %d\n" % (returnCode)
                for line in ddict['message']:
                    text += line
                msg.setText(text)
                msg.exec_()
                return

            xmsoFile = self._xrfmcFileNamesDict['xmso']
            corrections = XRFMCHelper.getXMSOFileFluorescenceInformation(xmsoFile)
            self.dict['result']['config']['xrfmc']['corrections'] = corrections
            elementsList = list(corrections.keys())
            elementsList.sort()
            for element in elementsList:
                for key in ['K', 'Ka', 'Kb', 'L', 'L1', 'L2', 'L3', 'M']:
                    if corrections[element][key]['total'] > 0.0:
                        value = corrections[element][key]['correction_factor'][-1]
                        if value != 1.0:
                            text = "%s %s xrays multiple excitation factor = %.3f" % \
                                   (element, key, value)                
                            self.logWidget.append(text)

            from PyMca.PyMcaIO import specfilewrapper as specfile
            sf = specfile.Specfile(self._xrfmcFileNamesDict['csv'])
            nScans = len(sf)
            scan = sf[nScans - 1]
            nMca = scan.nbmca()
            # specfile starts numbering at one
            # and the first mca corresponds to the energy
            self._xrfmcMatrixSpectra = []
            for i in range(1, nMca + 1):
                self._xrfmcMatrixSpectra.append(scan.mca(i))
            scan = None
            sf = None
            self.removeDirectory(self.__tmpMatrixSpectrumDir)
            #self.logWidget.hide()
            self.plot()
            ddict=copy.deepcopy(self.dict)
            ddict['event'] = "McaAdvancedFitXRFMCMatrixFinished"
            if 0:
                # this for later
                try:
                    self.__anasignal(ddict)
                except:
                    print("Error generating Monte Carlo matrix output. ")
                    print(sys.exc_info())
            

    def peaksSpectrum(self):
        if not self.__fitdone:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            text = "You need to perform a fit first\n"
            msg.setText(text)
            msg.exec_()
            return
        #fitresult = self.dict['result']
        fitresult = self.dict
        # force update
        self.mcafit.configure()
        groupsList = fitresult['result']['groups']
        if type(groupsList) != type([]):
            groupsList = [groupsList]

        nglobal    = len(fitresult['result']['parameters']) - len(groupsList)
        ddict=copy.deepcopy(self.dict)
        ddict['event'] = "McaAdvancedFitPeaksFinished"
        newparameters = fitresult['result']['fittedpar'] * 1
        for i in range(nglobal,len(fitresult['result']['parameters'])):
            newparameters[i] = 0.0
        for i in range(nglobal,len(fitresult['result']['parameters'])):
            group = fitresult['result']['parameters'][i]
            parameters    = newparameters * 1
            parameters[i] = fitresult['result']['fittedpar'][i]
            xmatrix = fitresult['result']['xdata']
            ymatrix = self.mcafit.mcatheory(parameters,xmatrix)
            ymatrix.shape =  [len(ymatrix),1]
            label = 'y'+group
            if self.mcafit.STRIP:
                ddict['result'][label]  = ymatrix + self.mcafit.zz
            else:
                ddict['result'][label]  = ymatrix
            ddict['result'][label].shape  = (len(ddict['result'][label]),)
            if self.peaksSpectrumButton.isChecked():
                self.dict['result'][label]= ddict['result'][label] * 1.0
        try:
            self.__anasignal(ddict)
        except:
            print("Error generating peaks output. ")
            print("Try to perform your fit again.  ")
            print(sys.exc_info())
            print("If error persists, please report this error.")
            print("ymatrix shape = ", ddict['result']['ymatrix'].shape)
            print("xmatrix shape = ", xmatrix.shape)
            print("continuum shape = ", ddict['result']['continuum'].shape)
            print("zz      shape = ", self.mcafit.zz.shape)

    def __printps(self):
        self.__printmenu.exec_(self.cursor().pos())

    def htmlReport(self,index=None):
        if not self.__fitdone:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            msg.setText("You should perform a fit \nfirst,\n shouldn't you?")
            msg.exec_()
            return
        oldoutdir = self.outdir
        if self.outdir is None:
            cwd = PyMcaDirs.outputDir
            outfile = qt.QFileDialog(self)
            outfile.setWindowTitle("Output Directory Selection")
            outfile.setModal(1)
            outfile.setFileMode(outfile.DirectoryOnly)
            outfile.setDirectory(cwd)
            ret = outfile.exec_()
            if ret:
                self.outdir = qt.safe_str(outfile.selectedFiles()[0])
                outfile.close()
                del outfile
            else:
                # pyflakes http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=666494
                outfile.close()
                del outfile
                return
            if self.outdir[-1]=="/":self.outdir=self.outdir[0:-1]
        try:
            self.__htmlReport()
        except IOError:
            self.outdir = None
            if oldoutdir is not None:
                if os.path.exists(oldoutdir):
                    self.outdir = oldoutdir
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            msg.setText("Input Output Error: %s" % (sys.exc_info()[1]))
            msg.exec_()

    def __htmlReport(self,outfile=None):
        report = QtMcaAdvancedFitReport.QtMcaAdvancedFitReport(None,
                    outfile,self.outdir,self.info['sourcename'],
                    self.info['legend'],self.dict,
                    concentrations=self._concentrationsDict,
                    plotdict={'logy':self._logY})
        if 0:
            #this forces to open and read the file
            self.__lastreport = report.writeReport()
        else:
            text = report.getText()
            self.__lastreport = report.writeReport(text=text)
        if self.browser is None:
            self.browser= qt.QWidget()
            self.browser.setWindowTitle(QString(self.__lastreport))
            self.browser.layout = qt.QVBoxLayout(self.browser)
            self.browser.layout.setContentsMargins(0, 0, 0, 0)
            self.browser.layout.setSpacing(0)
            self.__printmenu.addSeparator()
            self.__printmenu.addAction(QString("Last Report"),self.showLastReport)

            self.browsertext = qt.QTextBrowser(self.browser)
            self.browsertext.setReadOnly(1)
            screenWidth = qt.QDesktopWidget().width()
            if screenWidth > 0:
                self.browsertext.setMinimumWidth(min(self.width(), int(0.5 * screenWidth)))
            else:
                self.browsertext.setMinimumWidth(self.width())
            screenHeight = qt.QDesktopWidget().height()
            if screenHeight > 0:
                self.browsertext.setMinimumHeight(min(self.height(), int(0.5 * screenHeight)))
            else:
                self.browsertext.setMinimumHeight(self.height())

            self.browser.layout.addWidget(self.browsertext)
        else:
            self.browser.setWindowTitle(QString(self.__lastreport))

        dirname = os.path.dirname(self.__lastreport)
        # basename = os.path.basename(self.__lastreport)
        #self.browsertext.setMimeSourceFactory(qt.QMimeFactory.defaultFactory())
        #self.browsertext.mimeSourceFactory().addFilePath(QString(dirname))
        self.browsertext.setSearchPaths([QString(dirname)])
        #self.browsertext.setSource(qt.QUrl(QString(basename)))
        self.browsertext.clear()
        if QTVERSION < '4.2.0':
            self.browsertext.insertHtml(text)
        else:
            self.browsertext.setText(text)
        self.browsertext.show()
        self.showLastReport()

    def showLastReport(self):
        if self.browser is not None:
            self.browser.show()
            if QTVERSION < '4.0.0':
                self.browser.raiseW()
            else:
                self.browser.raise_()

    def printConcentrations(self, doit=0):
        text = "<CENTER>"+self.concentrationsWidget.concentrationsTable.getHtmlText()+"</CENTER>"
        if (__name__ == "__main__") or (doit):
            self.__print(text)
        else:
            ddict={}
            ddict['event'] = "McaAdvancedFitPrint"
            ddict['text' ] = text
            self.sigMcaAdvancedFitSignal.emit(ddict)

    def printps(self, doit=0):
        h = self.__htmlheader()
        text = "<CENTER>"+self.mcatable.gettext()+"</CENTER>"
        #text = self.mcatable.gettext()
        if (__name__ == "__main__") or (doit):
            self.__print(h+text)
            #print h+text
        else:
            ddict={}
            ddict['event'] = "McaAdvancedFitPrint"
            ddict['text' ] = h+text
            self.sigMcaAdvancedFitSignal.emit(ddict)

    def __htmlheader(self):
        header = "%s" % qt.safe_str(self.headerLabel.text())
        if header[0] == "<":
            header = header[3:-3]
        if self.mcafit.config['fit']['sumflag']:
            sumflag = "Y"
        else:
            sumflag = "N"

        if self.mcafit.config['fit']['escapeflag']:
            escapeflag =  "Y"
        else:
            escapeflag = "N"

        if self.mcafit.config['fit']['stripflag']:
            stripflag = "Y"
        else:
            stripflag = "N"
        #bkg = self.mcafit.config['fit']['continuum']
        #theory = "Hypermet"
        bkg    = "%s" % qt.safe_str(self.top.BkgComBox.currentText())
        theory = "%s" % qt.safe_str(self.top.FunComBox.currentText())
        hypermetflag=self.mcafit.config['fit']['hypermetflag']
        # g_term  = hypermetflag & 1
        st_term   = (hypermetflag >>1) & 1
        lt_term   = (hypermetflag >>2) & 1
        step_term = (hypermetflag >>3) & 1
        if st_term:
            st_term = "Y"
        else:
            st_term = "N"
        if st_term:
            lt_term = "Y"
        else:
            lt_term = "N"
        if step_term:
            step_term = "Y"
        else:
            step_term = "N"


        h=""
        h+="    <CENTER>"
        h+="<B>%s</B>" % header
        h+="    </CENTER>"
        h+="    <SPACER TYPE=BLOCK HEIGHT=10>"
        #h+="<BR></BR>"
        h+="    <CENTER>"
        h+="<TABLE>"
        h+="<TR>"
        h+="    <TD ALIGN=LEFT><B>Function</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD NOWRAP ALIGN=LEFT>%s</TD>" % theory
        h+="    <TD><SPACER TYPE=BLOCK WIDTH=15></TD>"

        h+="    <TD ALIGN=LEFT><B>ShortTail</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD>%s</TD>" % st_term
        h+="    <TD><SPACER TYPE=BLOCK WIDTH=5></B></TD>"

        h+="    <TD ALIGN=LEFT><B>LongTail</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD>%s</TD>" % lt_term
        h+="    <TD><SPACER TYPE=BLOCK WIDTH=5></B></TD>"

        h+="    <TD ALIGN=LEFT><B>StepTail</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD>%s</TD>" % step_term
        h+="</TR>"

        h+="<TR>"
        #h+="    <TD ALIGN=LEFT><B>Background</B></TH>"
        h+="    <TD ALIGN=LEFT><B>Backg.</B></TH>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD NOWRAP ALIGN=LEFT>%s</TD>" % bkg
        h+="    <TD><SPACER TYPE=BLOCK WIDTH=15></B></TD>"

        h+="    <TD ALIGN=LEFT><B>Escape</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD>%s</TD>" % escapeflag
        h+="    <TD><SPACER TYPE=BLOCK WIDTH=5></B></TD>"

        h+="    <TD ALIGN=LEFT><B>Pile-up</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD ALIGN=LEFT>%s</TD>" % sumflag
        h+="    <TD><SPACER TYPE=BLOCK WIDTH=5></B></TD>"

        h+="    <TD ALIGN=LEFT><B>Strip</B></TD>"
        h+="    <TD><B>:</B></TD>"
        h+="    <TD>%s</TD>" % stripflag

        h+="</TR>"
        h+="</TABLE>"
        h+="</CENTER>"
        return h


    if QTVERSION < '4.0.0':
        def __print(self,text):
            printer = qt.QPrinter()
            if printer.setup(self):
                painter = qt.QPainter()
                if not(painter.begin(printer)):
                    return 0
                metrics = qt.QPaintDeviceMetrics(printer)
                dpiy    = metrics.logicalDpiY()
                margin  = int((2/2.54) * dpiy) #2cm margin
                body = qt.QRect(0.5*margin, margin, metrics.width()- 1 * margin, metrics.height() - 2 * margin)
                #html output -> print text
                richtext = qt.QSimpleRichText(text, qt.QFont(),
                                                    QString(""),
                                                    #0,
                                                    qt.QStyleSheet.defaultSheet(),
                                                    qt.QMimeSourceFactory.defaultFactory(),
                                                    body.height())
                view = qt.QRect(body)
                richtext.setWidth(painter,view.width())
                page = 1
                while(1):
                    richtext.draw(painter,body.left(),body.top(),
                                view,qt.QColorGroup())
                    view.moveBy(0, body.height())
                    painter.translate(0, -body.height())
                    painter.drawText(view.right()  - painter.fontMetrics().width(QString.number(page)),
                                     view.bottom() - painter.fontMetrics().ascent() + 5,QString.number(page))
                    if view.top() >= richtext.height():
                        break
                    printer.newPage()
                    page += 1

                #painter.flush()
                painter.end()
    else:
        # pyflakes http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=666503
        def __print(self,text):
            printer = qt.QPrinter()
            printDialog = qt.QPrintDialog(printer, self)
            if printDialog.exec_():
                if 0:
                    #this was crashing in Qt 4.2.2
                    #with the PyQt snapshot of 20061203
                    editor = qt.QTextEdit()
                    cursor = editor.textCursor()
                    cursor.movePosition(qt.QTextCursor.Start)
                    editor.insertHtml(text)
                    document = editor.document()
                else:
                    document = qt.QTextDocument()
                    document.setHtml(text)
                document.print_(printer)

    def setdata(self, *var, **kw):
        if DEBUG:
            print("McaAdvancedFit.setdata deprecated, use setData instead.")
        return self.setData( *var, **kw)

    def setData(self,*var,**kw):
        """
        The simplest way to use it is to pass at least the y keyword containing
        the channel counts. The other items are not mandatory.
        
        :keywords:
            x
                channels
            y
                counts in each channel
            sigmay
                uncertainties to be applied if different than sqrt(y)
            xmin
                minimum channel of the fit
            xmax
                maximum channel of the fit
            calibration
                list of the form [a, b, c] containing the mca calibration 
        """
        
        self.__fitdone = 0
        self.info ={}
        key = 'legend'
        if key in kw:
            self.info[key] = kw[key]
        else:
            self.info[key] = 'Unknown Origin'
        key = 'xlabel'
        if key in kw:
            self.info[key] = kw[key]
        else:
            self.info[key] = 'X'
        key = 'xmin'
        if key in kw:
            self.info[key] = "%.3f" % kw[key]
        else:
            self.info[key] = "????"
        key = 'xmax'
        if key in kw:
            self.info[key] = "%.3f" % kw[key]
        else:
            self.info[key] = "????"
        key = 'sourcename'
        if key in kw:
            self.info[key] = "%s" % kw[key]
        else:
            self.info[key] = "Unknown Source"
        self.__var = var
        self.__kw  = kw
        self.mcafit.setData(*var,**kw)
        if self.configDialog is not None:
            self.configDialog.setData(self.mcafit.xdata * 1.0,
                           self.mcafit.ydata * 1.0)

        if 'calibration' in kw:
            if kw['calibration'] is not None:
                # The condition below gave troubles because it was using the
                # current calibration even if the x data where actual energies.
                # if (kw['calibration'] != [0.0,1.0,0.0]):
                self.mcafit.config['detector']['zero']=kw['calibration'][0] * 1
                self.mcafit.config['detector']['gain']=kw['calibration'][1] * 1

        self.setHeader(text="Fit of %s from %s %s to %s" % (self.info['legend'],
                                                            self.info['xlabel'],
                                                            self.info['xmin'],
                                                            self.info['xmax']))
        self._updateTop()
        self.plot()

    def setheader(self, *var, **kw):
        if DEBUG:
            print("McaAdvancedFit.setheader deprecated, use setHeader instead.")
        return self.setHeader( *var, **kw)

    def setHeader(self,*var,**kw):
        if len(var):
            text = var[0]
        elif 'text' in kw:
            text = kw['text']
        elif 'header' in kw:
            text = kw['header']
        else:
            text = ""
        self.headerLabel.setText("%s" % text)

    def fit(self):
        """
        Function called to start the fit process.
        
        Interactive use
                
        It returns a dictionnary containing the fit results or None in case of 
        unsuccessfull fit.
        
        Embedded use
        
        In case of successfull fit emits a signal of the form:
            
        self.emit(qt.SIGNAL('McaAdvancedFitSignal'), (ddict))
        
        where ddict['event'] = 'McaAdvancedFitFinished'
        """    
        self.__fitdone = 0
        self.mcatable.setRowCount(0)
        if self.concentrationsWidget is not None:
            self.concentrationsWidget.concentrationsTable.setRowCount(0)
        fitconfig = {}
        fitconfig.update(self.mcafit.configure())
        if fitconfig['peaks'] == {}:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Information)
            msg.setText("No peaks defined.\nPlease configure peaks")
            if QTVERSION < '4.0.0':
                msg.exec_loop()
            else:
                msg.exec_()
            return
        if DEBUG:
            if DEBUG:
                print("calling estimate")
            self.mcafit.estimate()
            if DEBUG:
                print("calling startfit")
            fitresult,result = self.mcafit.startfit(digest=1)
            if DEBUG:
                print("filling table")
            self.mcatable.fillfrommca(result)
            if DEBUG:
                print("finished")
        else:
            try:
                self.mcafit.estimate()
                threadResult = self._submitThread(self.mcafit.startfit,
                                            {'digest':1},
                                            "Calculating Fit",
                                            True)
                if type(threadResult) == type((1,)):
                    if len(threadResult):
                        if threadResult[0] == "Exception":
                            raise Exception(threadResult[1], threadResult[2])
                fitresult = threadResult[0]
                result    = threadResult[1]
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setWindowTitle("Fit error")
                msg.setText("Error on fit:")
                msg.setInformativeText(str(sys.exc_info()[1]))
                msg.setDetailedText(traceback.format_exc())
                msg.exec_()
                msg.exec_()
                return
            try:
                #self.mcatable.fillfrommca(self.mcafit.result)
                self.mcatable.fillfrommca(result)
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Error filling Table: %s" % (sys.exc_info()[1]))
                msg.exec_()
                return
        dict={}
        dict['event']     = "McaAdvancedFitFinished"
        dict['fitresult'] = fitresult
        dict['result']    = result
        #I should make a copy but ...
        self.dict = {}
        self.dict['info'] = {}
        self.dict['info'] = self.info.copy()
        self.dict['result'] = dict['result']
        self.__fitdone      = 1
        # add the matrix spectrum
        if self.matrixSpectrumButton.isChecked():
            self.matrixSpectrum()
        else:
            if "Matrix" in self.graph.getAllCurves(just_legend=True):
                self.graph.removeCurve("Matrix")

        # clear the Monte Carlo spectra (if any)
        self._xrfmcMatrixSpectra = None

        # add the peaks spectrum
        if self.peaksSpectrumButton.isChecked():
            self.peaksSpectrum()
        else:
            self.__clearPeaksSpectrum()
        self.plot()

        if self.concentrationsWidget is not None:
            if (str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == 'CONCENTRATIONS') or \
                (self.concentrationsWidget.parent() is None):
                if not self.concentrationsWidget.isHidden():
                    if DEBUG:
                        self.concentrations()
                    else:
                        try:
                            self.concentrations()
                        except:
                            msg = qt.QMessageBox(self)
                            msg.setIcon(qt.QMessageBox.Critical)
                            msg.setText("Concentrations Error: %s" % (sys.exc_info()[1]))
                            msg.exec_()
                            return
        if str(self.mainTab.tabText(self.mainTab.currentIndex())).upper() == 'DIAGNOSTICS':
            try:
                self.diagnostics()
            except:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Diagnostics Error: %s" % (sys.exc_info()[1]))
                msg.exec_()
                return

        return self.__anasignal(dict)

    def __anasignal(self, ddict):
        if type(ddict) != type({}):
            return
        if 'event' in ddict:
            ddict['info'] = {}
            ddict['info'].update(self.info)
            self.sigMcaAdvancedFitSignal.emit(ddict)
            #Simplify interactive usage of the module
            return ddict

    def dismiss(self):
        self.close()

    def closeEvent(self, event):
        if self.identifier is not None:
            self.identifier.close()
        qt.QWidget.closeEvent(self, event)

    def _mcaGraphSignalSlot(self, ddict):
        if ddict['event'] == "FitClicked":
            self.fit()
        elif ddict['event'] == "EnergyClicked":
            self.toggleEnergyAxis()
        elif ddict['event'] == "SaveClicked":
            self._saveGraph()
        elif ddict['event'].lower() in ["mouseclicked", "curveclicked"]:
            if ddict['button'] == 'left':
                if self._energyAxis:
                    self.__peakIdentifier(ddict['x'])
        else:
            pass
        return

    def toggleEnergyAxis(self, dict=None):
        if self._energyAxis:
            self._energyAxis = False
            self.graph.setGraphXLabel('Channel')
        else:
            self._energyAxis = True
            self.graph.setGraphXLabel('Energy')
        self.plot()

    def plot(self, ddict=None):
        if self._logY:
            logfilter = 1
        else:
            logfilter = 0
        config = self.mcafit.configure()
        if ddict is None:
            if not self.__fitdone:
                #just the data
                xdata  = self.mcafit.xdata * 1.0
                if self._energyAxis:
                    xdata = config['detector'] ['zero'] + config['detector'] ['gain'] * xdata
                if self.mcafit.STRIP:
                    ydata  = self.mcafit.ydata + self.mcafit.zz
                else:
                    ydata  = self.mcafit.ydata * 1.0
                xdata.shape= [len(xdata),]
                ydata.shape= [len(ydata),]
                self.graph.addCurve(xdata, ydata, legend="Data", replot=True, replace=True)
                self.graph.updateLegends()
                return
            else:
                ddict = self.dict
        if self._energyAxis:
            xdata = ddict['result']['energy'][:]
        else:
            xdata = ddict['result']['xdata'][:]
        self.graph.addCurve(xdata, ddict['result']['ydata'], legend="Data", replot=False)
        self.graph.addCurve(xdata, ddict['result']['yfit'], legend="Fit", replot=True)
        self.graph.addCurve(xdata, ddict['result']['continuum'], legend="Continuum", replot=True)

        curveList = self.graph.getAllCurves(just_legend=True)

        if config['fit']['sumflag']:
            self.graph.addCurve(xdata, ddict['result']['pileup'] + ddict['result']['continuum'],
                                legend="Pile-up", replot=True)
        elif "Pile-up" in curveList:
            self.graph.removeCurve("Pile-up", replot=True)

        if self.matrixSpectrumButton.isChecked():
            if 'ymatrix' in ddict['result']:
                self.graph.addCurve(xdata, ddict['result']['ymatrix'], legend="Matrix")
            else:
                self.graph.removeCurve("Matrix")
        else:
            self.graph.removeCurve("Matrix")

        if self._xrfmcMatrixSpectra is not None:
            if len(self._xrfmcMatrixSpectra):
                if self._energyAxis:
                    mcxdata = self._xrfmcMatrixSpectra[1]
                else:
                    mcxdata = self._xrfmcMatrixSpectra[0]
                mcydata0 = self._xrfmcMatrixSpectra[2]
                mcydatan = self._xrfmcMatrixSpectra[-1]
                self.graph.addCurve(mcxdata,
                                    mcydata0,
                                    legend='MC Matrix 1',
                                    replot=False)
                self.graph.addCurve(mcxdata,
                                    mcydatan,
                                    legend='MC Matrix %d' % (len(self._xrfmcMatrixSpectra) - 2),
                                    replot=True)

        if self.peaksSpectrumButton.isChecked():
            keep = ['Data','Fit','Continuum','Matrix','Pile-up']
            for group in ddict['result']['groups']:
                keep += ['y'+group]
            for key in curveList:
                if key not in keep:
                    if key.startswith('MC Matrix'):
                        if self._xrfmcMatrixSpectra in [None, []]:
                            self.graph.removeCurve(key)
                    else:
                        self.graph.removeCurve(key)
            for group in ddict['result']['groups']:
                label = 'y'+group
                if label in ddict['result']:
                    self.graph.addCurve(xdata,
                                        ddict['result'][label],
                                        legend=label,
                                        replot=False)
                else:
                    if group in curveList:
                        self.graph.removeCurve(label, replot=False)
        else:
            self.__clearPeaksSpectrum()

        self.graph.replot()
        self.graph.updateLegends()

    def _saveGraph(self, dict=None):
        curves = self.graph.curves.keys()
        if not len(curves):return
        if not self.__fitdone:
            if False:
                # just save the data ?
                # just save data plus strip background if any?
                # for the time being just force to have the fit
                pass
            else:
                msg = qt.QMessageBox(self)
                msg.setIcon(qt.QMessageBox.Critical)
                text = "Sorry, You need to perform a fit first.\n"
                msg.setText(text)
                if QTVERSION < '4.0.0':
                    msg.exec_loop()
                else:
                    msg.exec_()
                return
        if dict is None:
            #everything
            fitresult = self.dict
        else:
            fitresult = dict
        xdata     = fitresult['result']['xdata']
        # energy    = fitresult['result']['energy']
        # ydata     = fitresult['result']['ydata']
        # yfit      = fitresult['result']['yfit']
        # continuum = fitresult['result']['continuum']
        # pileup    = fitresult['result']['pileup']
        # savelist  = ['xdata', 'energy','ydata','yfit','continuum','pileup']
        # parNames  = fitresult['result']['parameters']
        # parFit    = fitresult['result']['fittedpar']
        # parSigma  = fitresult['result']['sigmapar']

        #still to add the matrix spectrum

        #get outputfile
        outfile = qt.QFileDialog(self)
        outfile.setModal(1)
        if self.lastInputDir is None:
            self.lastInputDir = PyMcaDirs.outputDir
        if QTVERSION < '4.0.0':
            outfile.setCaption("Output File Selection")
            filterlist = 'Specfile MCA  *.mca\nSpecfile Scan *.dat\nRaw ASCII  *.txt'
            if MATPLOTLIB:
                filterlist += '\nGraphics EPS *.eps\nGraphics PNG *.png'
                if not self.peaksSpectrumButton.isChecked():
                    filterlist += '\nB/WGraphics EPS *.eps\nB/WGraphics PNG *.png'
            outfile.setFilters(filterlist)
            outfile.setMode(outfile.AnyFile)
            outfile.setDir(self.lastInputDir)
            ret = outfile.exec_loop()
        else:
            outfile.setWindowTitle("Output File Selection")
            if hasattr(qt, "QStringList"):
                strlist = qt.QStringList()
            else:
                strlist = []
            format_list = ['Specfile MCA  *.mca',
                           'Specfile Scan *.dat',
                           'Raw ASCII  *.txt',
                           '";"-separated CSV *.csv',
                           '","-separated CSV *.csv',
                           '"tab"-separated CSV *.csv']
            if MATPLOTLIB:
                format_list.append('Graphics PNG *.png')
                format_list.append('Graphics EPS *.eps')
                format_list.append('Graphics SVG *.svg')
                if not self.peaksSpectrumButton.isChecked():
                    format_list.append('B/WGraphics PNG *.png')
                    format_list.append('B/WGraphics EPS *.eps')
                    format_list.append('B/WGraphics SVG *.svg')
            for f in format_list:
                strlist.append(f)
            outfile.setFilters(strlist)

            outfile.setFileMode(outfile.AnyFile)
            outfile.setAcceptMode(qt.QFileDialog.AcceptSave)
            outfile.setDirectory(self.lastInputDir)
            ret = outfile.exec_()

        if ret:
            filterused = qt.safe_str(outfile.selectedFilter()).split()
            filedescription = filterused[0]
            filetype  = filterused[1]
            extension = filterused[2]
            if QTVERSION < '4.0.0':
                outstr = qt.safe_str(outfile.selectedFile())
            else:
                outstr = qt.safe_str(outfile.selectedFiles()[0])
            try:
                outputDir  = os.path.dirname(outstr)
                self.lastInputDir   = outputDir
                PyMcaDirs.outputDir = outputDir
            except:
                outputDir  = "."
            #self.outdir = outputDir
            try:
                outputFile = os.path.basename(outstr)
            except:
                outputFile  = outstr
            outfile.close()
            del outfile
        else:
            # pyflakes bug http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=666494
            outfile.close()
            del outfile
            return
        #always overwrite for the time being
        if len(outputFile) < len(extension[1:]):
            outputFile += extension[1:]
        elif outputFile[-4:] != extension[1:]:
            outputFile += extension[1:]
        specFile = os.path.join(outputDir, outputFile)
        try:
            os.remove(specFile)
        except:
            pass
        systemline = os.linesep
        os.linesep = '\n'
        try:
            if MATPLOTLIB:
                if filetype in ['EPS', 'PNG', 'SVG']:
                    size = (7, 3.5) #in inches
                    logy = self._logY
                    if filedescription == "B/WGraphics":
                        bw = True
                    else:
                        bw = False
                    if self.peaksSpectrumButton.isChecked():  legends = True
                    elif 'ymatrix' in fitresult['result'].keys(): legends = False
                    else: legends = False
                    if self.matplotlibDialog is None:
                        self.matplotlibDialog = QPyMcaMatplotlibSave1D.\
                                                QPyMcaMatplotlibSaveDialog(size=size,
                                                                    logy=logy,
                                                                    legends=legends,
                                                                    bw = bw)
                    mtplt = self.matplotlibDialog.plot
                    mtplt.setParameters({'logy':logy,
                                         'legends':legends,
                                         'bw':bw})
                    """
                        mtplt = PyMcaMatplotlibSave.PyMcaMatplotlibSave(size=size,
                                                                    logy=logy,
                                                                    legends=legends,
                                                                    bw = bw)
                        self.matplotlibDialog = None
                    """
                    if self._energyAxis:
                        x = fitresult['result']['energy']
                    else:
                        x = fitresult['result']['xdata']
                    xmin, xmax = self.graph.getx1axislimits()
                    ymin, ymax = self.graph.gety1axislimits()
                    mtplt.setLimits(xmin, xmax, ymin, ymax)
                    index = numpy.nonzero((xmin <= x) & (x <= xmax))[0]
                    x = numpy.take(x, index)
                    if bw:
                        mtplt.addDataToPlot( x,
                                numpy.take(fitresult['result']['ydata'],index),
                                legend='data',
                                color='k',linestyle=':', linewidth=1.5, markersize=3)
                    else:
                        mtplt.addDataToPlot( x,
                                numpy.take(fitresult['result']['ydata'],index),
                                legend='data',
                                linewidth=1)

                    mtplt.addDataToPlot( x,
                                numpy.take(fitresult['result']['yfit'],index),
                                legend='fit',
                                linewidth=1.5)
                    if not self.peaksSpectrumButton.isChecked():
                        mtplt.addDataToPlot( x,
                                    numpy.take(fitresult['result']['continuum'],index),
                                    legend='bck', linewidth=1.5)
                    if self.top.sumbox.isChecked():
                        mtplt.addDataToPlot( x,
                                numpy.take(fitresult['result']['pileup']+\
                                             fitresult['result']['continuum'],index),
                                             legend="pile up",
                                             linewidth=1.5)
                    if 'ymatrix' in fitresult['result'].keys():
                        mtplt.addDataToPlot( x,
                                numpy.take(fitresult['result']['ymatrix'],index),
                                legend='matrix',
                                linewidth=1.5)
                    if self._xrfmcMatrixSpectra is not None:
                        if len(self._xrfmcMatrixSpectra):
                            if self._energyAxis:
                                mcxdata = self._xrfmcMatrixSpectra[1]
                            else:
                                mcxdata = self._xrfmcMatrixSpectra[0]
                            mcindex = numpy.nonzero((xmin <= mcxdata) & (mcxdata <= xmax))[0]
                            mcxdatax = numpy.take(mcxdata, mcindex)
                            mcydata0 = numpy.take(self._xrfmcMatrixSpectra[2], mcindex)
                            mcydatan = numpy.take(self._xrfmcMatrixSpectra[-1], mcindex)
                            mtplt.addDataToPlot(mcxdatax,
                                                mcydata0,
                                                legend='MC Matrix 1',
                                                linewidth=1.5)
                            mtplt.addDataToPlot(mcxdatax,
                                                mcydatan,
                                                legend='MC Matrix %d' % (len(self._xrfmcMatrixSpectra) - 2),
                                                linewidth=1.5)
                    if self.peaksSpectrumButton.isChecked():
                        for group in fitresult['result']['groups']:
                            label = 'y'+group
                            if label in fitresult['result'].keys():
                                mtplt.addDataToPlot( x,
                                    numpy.take(fitresult['result'][label],index),
                                                legend=group,
                                                linewidth=1.5)
                    if self._energyAxis:
                        mtplt.setXLabel('Energy (keV)')
                    else:
                        mtplt.setXLabel('Channel')
                    mtplt.setYLabel('Counts')
                    mtplt.plotLegends()
                    if self.matplotlibDialog is not None:
                        ret = self.matplotlibDialog.exec_()
                        if ret == qt.QDialog.Accepted:
                            mtplt.saveFile(specFile)
                    else:
                        mtplt.saveFile(specFile)
                    return
        except:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            msg.setText("Matplotlib or Input Output Error: %s" % (sys.exc_info()[1]))
            if QTVERSION < '4.0.0':
                msg.exec_loop()
            else:
                msg.exec_()
            return
        try:
            file=open(specFile,'wb')
        except IOError:
            msg = qt.QMessageBox(self)
            msg.setIcon(qt.QMessageBox.Critical)
            msg.setText("Input Output Error: %s" % (sys.exc_info()[1]))
            if QTVERSION < '4.0.0':
                msg.exec_loop()
            else:
                msg.exec_()
            return
        try:
            if filetype == 'ASCII':
                keys = fitresult['result'].keys()
                for i in range(len(fitresult['result']['ydata'])):
                    file.write("%.7g  %.7g   %.7g  %.7g  %.7g  %.7g" % (fitresult['result']['xdata'][i],
                                       fitresult['result']['energy'][i],
                                       fitresult['result']['ydata'][i],
                                       fitresult['result']['yfit'][i],
                                       fitresult['result']['continuum'][i],
                                       fitresult['result']['pileup'][i]))
                    if 'ymatrix' in fitresult['result'].keys():
                        file.write("  %.7g" %  fitresult['result']['ymatrix'][i])
                    for group in fitresult['result']['groups']:
                        label = 'y'+group
                        if label in keys:
                            file.write("  %.7g" %  fitresult['result'][label][i])
                    file.write("\n")
                file.close()
                return
            if filetype == 'CSV':
                if "," in filterused[0]:
                    csv = ","
                elif ";" in filterused[0]:
                    csv = ";"
                else:
                    csv = "\t"
                keys = fitresult['result'].keys()

                headerLine = '"channel"%s"Energy"%s"counts"%s"fit"%s"continuum"%s"pileup"' % (csv, csv, csv, csv, csv)
                if 'ymatrix' in keys:
                    headerLine += '%s"ymatrix"' % csv

                for group in fitresult['result']['groups']:
                    label = 'y'+group
                    if label in keys:
                        headerLine += csv+ ('"%s"' % group)
                file.write(headerLine)
                file.write('\n')
                for i in range(len(fitresult['result']['ydata'])):
                    file.write("%.7g%s%.7g%s%.7g%s%.7g%s%.7g%s%.7g" % (fitresult['result']['xdata'][i],
                                       csv,
                                       fitresult['result']['energy'][i],
                                       csv,
                                       fitresult['result']['ydata'][i],
                                       csv,
                                       fitresult['result']['yfit'][i],
                                       csv,
                                       fitresult['result']['continuum'][i],
                                       csv,
                                       fitresult['result']['pileup'][i]))
                    if 'ymatrix' in fitresult['result'].keys():
                        file.write("%s%.7g" %  (csv,fitresult['result']['ymatrix'][i]))
                    for group in fitresult['result']['groups']:
                        label = 'y'+group
                        if label in keys:
                            file.write("%s%.7g" %  (csv,fitresult['result'][label][i]))
                    file.write("\n")
                file.close()
                return
            #header is almost common to specfile and mca
            file.write("#F %s\n" % specFile)
            file.write("#D %s\n"%(time.ctime(time.time())))
            file.write("\n")
            legend = str(self.headerLabel.text()).strip('<b>')
            legend.strip('<\b>')
            file.write("#S 1 %s\n" % legend)
            file.write("#D %s\n"%(time.ctime(time.time())))
            i = 0
            for parameter in fitresult['result']['parameters']:
                file.write("#U%d %s %.7g +/- %.3g\n" % (i, parameter,
                                                     fitresult['result']['fittedpar'][i],
                                                     fitresult['result']['sigmapar'][i]))
                i+=1
            if filetype == 'Scan':
                keys = fitresult['result'].keys()
                labelline= "#L channel  Energy  counts  fit  continuum  pileup"
                if 'ymatrix' in keys:
                    nlabels = 7
                    labelline += "ymatrix"
                else:
                    nlabels = 6

                for group in fitresult['result']['groups']:
                    label = 'y'+group
                    if label in keys:
                        nlabels += 1
                        labelline += '  '+group
                file.write("#N %d\n" % nlabels)
                file.write(labelline)
                file.write("\n")
                for i in range(len(fitresult['result']['ydata'])):
                    file.write("%.7g  %.7g  %.7g  %.7g  %.7g  %.7g" % (fitresult['result']['xdata'][i],
                                       fitresult['result']['energy'][i],
                                       fitresult['result']['ydata'][i],
                                       fitresult['result']['yfit'][i],
                                       fitresult['result']['continuum'][i],
                                       fitresult['result']['pileup'][i]))
                    if 'ymatrix' in keys:
                        file.write("  %.7g" % fitresult['result']['ymatrix'][i])
                    for group in fitresult['result']['groups']:
                        label = 'y'+group
                        if label in keys:
                            file.write("  %.7g" %  fitresult['result'][label][i])
                    file.write("\n")
            else:
                file.write("#@MCA %16C\n")
                file.write("#@CHANN %d %d %d 1\n" %  (len(fitresult['result']['ydata']),
                                                        fitresult['result']['xdata'][0],
                                                        fitresult['result']['xdata'][-1]))
                zeroindex = fitresult['result']['parameters'].index('Zero')
                gainindex = fitresult['result']['parameters'].index('Gain')
                file.write("#@CALIB %.7g %.7g 0.0\n" % (fitresult['result']['fittedpar'][zeroindex],
                                                        fitresult['result']['fittedpar'][gainindex]))
                file.write(self.array2SpecMca(fitresult['result']['ydata']))
                file.write(self.array2SpecMca(fitresult['result']['yfit']))
                file.write(self.array2SpecMca(fitresult['result']['continuum']))
                file.write(self.array2SpecMca(fitresult['result']['pileup']))
                keys = fitresult['result'].keys()
                if 'ymatrix' in keys:
                    file.write(self.array2SpecMca(fitresult['result']['ymatrix']))
                for group in fitresult['result']['groups']:
                    label = 'y'+group
                    if label in keys:
                        file.write(self.array2SpecMca(fitresult['result'][label]))
            file.write("\n")
            file.close()
        except:
            os.linesep = systemline
            raise
        return

    def array2SpecMca(self, data):
        """ Write a python array into a Spec array.
            Return the string containing the Spec array
        """
        tmpstr = "@A "
        length = len(data)
        for idx in range(0, length, 16):
            if idx+15 < length:
                for i in range(0,16):
                    tmpstr += "%.4f " % data[idx+i]
                if idx+16 != length:
                    tmpstr += "\\"
            else:
                for i in range(idx, length):
                    tmpstr += "%.4f " % data[i]
            tmpstr += "\n"
        return tmpstr


class Top(qt.QWidget):
    def __init__(self,parent = None,name = None,fl = 0):
        qt.QWidget.__init__(self,parent)
        self.mainLayout= qt.QHBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)
        self.build()

    def build(self):
        self.__w=qt.QWidget(self)
        w = self.__w
        self.mainLayout.addWidget(w)
        wlayout = qt.QGridLayout(w)
        wlayout.setSpacing(5)
        #function
        FunLabel = qt.QLabel(w)
        FunLabel.setText(str("Function"))
        if QTVERSION < '4.0.0':
            self.FunComBox = qt.QComboBox(0,w,"FunComBox")
            self.FunComBox.insertStrList(["Mca Hypermet"])
            self.FunComBox.insertStrList(["Mca Pseudo-Voigt"])
        else:
            self.FunComBox = qt.QComboBox(w)
            self.FunComBox.insertItem(0, "Mca Hypermet")
            self.FunComBox.insertItem(1, "Mca Pseudo-Voigt")
        wlayout.addWidget(FunLabel,0,0)
        wlayout.addWidget(self.FunComBox,0,1)
        #background
        BkgLabel = qt.QLabel(w)
        BkgLabel.setText(str("Background"))
        if QTVERSION < '4.0.0':
            self.BkgComBox = qt.QComboBox(0,w,"BkgComBox")
            self.BkgComBox.insertStrList(['No Background',
                                          'Constant',
                                          'Linear',
                                          'Parabolic',
                                          'Linear Polynomial',
                                          'Exp. Polynomial'])
        else:
            self.BkgComBox = qt.QComboBox(w)
            options = ['No Background',
                       'Constant',
                       'Linear',
                       'Parabolic',
                       'Linear Polynomial',
                       'Exp. Polynomial']
            for item in options:
                self.BkgComBox.insertItem(options.index(item), item)

        self.connect(self.FunComBox,
                     qt.SIGNAL("activated(int)"),self.mysignal)

        self.connect(self.BkgComBox,
                     qt.SIGNAL("activated(int)"),self.mysignal)
        #                        qt.SIGNAL("activated(const QString &)"),self.bkgevent)
        wlayout.addWidget(BkgLabel,1,0)
        wlayout.addWidget(self.BkgComBox,1,1)
        dummy = qt.QWidget(self)
        dummy.setMinimumSize(20,0)
        self.mainLayout.addWidget(dummy)
        self.mainLayout.addWidget(qt.HorizontalSpacer(self))

        #the checkboxes
        if 0:
             w1 = qt.QVBox(self)
             self.WeightCheckBox = qt.QCheckBox(w1)
             self.WeightCheckBox.setText(str("Weight"))
             self.McaModeCheckBox = qt.QCheckBox(w1)
             self.McaModeCheckBox.setText(str("Mca Mode"))

        # Flags
        f       = qt.QWidget(self)
        self.mainLayout.addWidget(f)
        f.layout= qt.QGridLayout(f)
        f.layout.setSpacing(5)
        flagsoffset = -1
        coffset     = 0
        #hyplabel = qt.QLabel(f)
        #hyplabel.setText(str("<b>%s</b>" % 'FLAGS'))
        self.stbox = qt.QCheckBox(f)
        self.stbox.setText('Short Tail')
        self.ltbox = qt.QCheckBox(f)
        self.ltbox.setText('Long Tail')
        self.stepbox = qt.QCheckBox(f)
        self.stepbox.setText('Step Tail')
        self.escapebox = qt.QCheckBox(f)
        self.escapebox.setText('Escape')
        self.sumbox = qt.QCheckBox(f)
        self.sumbox.setText('Pile-up')
        self.stripbox = qt.QCheckBox(f)
        self.stripbox.setText('Strip Back.')
        #checkbox connections
        self.connect(self.stbox,qt.SIGNAL("clicked()"),     self.mysignal)
        self.connect(self.ltbox,qt.SIGNAL("clicked()"),     self.mysignal)
        self.connect(self.stepbox,qt.SIGNAL("clicked()"),   self.mysignal)
        self.connect(self.escapebox,qt.SIGNAL("clicked()"), self.mysignal)
        self.connect(self.sumbox,qt.SIGNAL("clicked()"),    self.mysignal)
        self.connect(self.stripbox,qt.SIGNAL("clicked()"),  self.mysignal)
        #f.layout.addWidget(hyplabel,flagsoffset,coffset +1)
        f.layout.addWidget(self.stbox,flagsoffset+1,coffset +0)
        f.layout.addWidget(self.ltbox,flagsoffset+1,coffset +1)
        f.layout.addWidget(self.stepbox,flagsoffset+1,coffset +2)
        f.layout.addWidget(self.escapebox,flagsoffset+2,coffset +0)
        f.layout.addWidget(self.sumbox,flagsoffset+2,coffset +1)
        f.layout.addWidget(self.stripbox,flagsoffset+2,coffset +2)
        self.mainLayout.addWidget(qt.HorizontalSpacer(self))

        #buttons
        g = qt.QWidget(self)
        self.mainLayout.addWidget(g)
        glayout = qt.QGridLayout(g)
        glayout.setSpacing(5)
        self.configureButton = qt.QPushButton(g)
        self.configureButton.setText(str("Configure"))
        self.printButton = qt.QPushButton(g)
        self.printButton.setText(str("Tools"))
        glayout.addWidget(self.configureButton,0,0)
        glayout.addWidget(self.printButton,1,0)

    def setParameters(self,ddict=None):
        if ddict == None: ddict = {}
        hypermetflag = ddict.get('hypermetflag', 1)
        if not ('fitfunction' in ddict):
            if hypermetflag:
                ddict['fitfunction'] = 0
            else:
                ddict['fitfunction'] = 1

        if QTVERSION < '4.0.0':
            self.FunComBox.setCurrentItem(ddict['fitfunction'])
        else:
            self.FunComBox.setCurrentIndex(ddict['fitfunction'])

        if 'hypermetflag' in ddict:
            hypermetflag = ddict['hypermetflag']
            if ddict['fitfunction'] == 0:
                # g_term  = hypermetflag & 1
                st_term   = (hypermetflag >>1) & 1
                lt_term   = (hypermetflag >>2) & 1
                step_term = (hypermetflag >>3) & 1
                self.stbox.setEnabled(1)
                self.ltbox.setEnabled(1)
                self.stepbox.setEnabled(1)
                if st_term:
                    self.stbox.setChecked(1)
                else:
                    self.stbox.setChecked(0)
                if lt_term:
                    self.ltbox.setChecked(1)
                else:
                    self.ltbox.setChecked(0)
                if step_term:
                    self.stepbox.setChecked(1)
                else:
                    self.stepbox.setChecked(0)
            else:
                self.stbox.setEnabled(0)
                self.ltbox.setEnabled(0)
                self.stepbox.setEnabled(0)

        key = 'sumflag'
        if key in ddict:
            if ddict[key] == 1:
                self.sumbox.setChecked(1)
            else:
                self.sumbox.setChecked(0)

        key = 'stripflag'
        if key in ddict:
            if ddict[key] == 1:
                self.stripbox.setChecked(1)
            else:
                self.stripbox.setChecked(0)

        key = 'escapeflag'
        if key in ddict:
            if ddict[key] == 1:
                self.escapebox.setChecked(1)
            else:
                self.escapebox.setChecked(0)

        key = 'continuum'
        if key in ddict:
            if QTVERSION < '4.0.0':
                self.BkgComBox.setCurrentItem(ddict[key])
            else:
                self.BkgComBox.setCurrentIndex(ddict[key])

    def getParameters(self):
        ddict={}
        if QTVERSION < '4.0.0':
            index = self.FunComBox.currentItem()
        else:
            index = self.FunComBox.currentIndex()

        ddict['fitfunction'] = index
        ddict['hypermetflag'] = 1
        if index == 0:
            self.stbox.setEnabled(1)
            self.ltbox.setEnabled(1)
            self.stepbox.setEnabled(1)
        else:
            ddict['hypermetflag'] = 0
            self.stbox.setEnabled(0)
            self.ltbox.setEnabled(0)
            self.stepbox.setEnabled(0)

        if self.stbox.isChecked():
            ddict['hypermetflag'] += 2
        if self.ltbox.isChecked():
            ddict['hypermetflag'] += 4

        if self.stepbox.isChecked():
            ddict['hypermetflag'] += 8

        if self.sumbox.isChecked():
            ddict['sumflag'] = 1
        else:
            ddict['sumflag'] = 0

        if self.stripbox.isChecked():
            ddict['stripflag'] = 1
        else:
            ddict['stripflag'] = 0

        if self.escapebox.isChecked():
            ddict['escapeflag'] = 1
        else:
            ddict['escapeflag'] = 0
        if QTVERSION < '4.0.0':
            ddict['continuum'] = self.BkgComBox.currentItem()
        else:
            ddict['continuum'] = self.BkgComBox.currentIndex()
        return ddict

    def mysignal(self,*var):
        ddict = self.getParameters()
        self.emit(qt.SIGNAL('TopSignal'),(ddict))


class Line(qt.QFrame):
    def __init__(self, parent=None, name="Line", fl=0, info=None):
        qt.QFrame.__init__(self, parent)
        self.info = info
        self.setFrameShape(qt.QFrame.HLine)
        self.setFrameShadow(qt.QFrame.Sunken)
        self.setFrameShape(qt.QFrame.HLine)


    def mouseDoubleClickEvent(self, event):
        if DEBUG:
            print("Double Click Event")
        ddict={}
        ddict['event']="DoubleClick"
        ddict['data'] = event
        ddict['info'] = self.info
        self.emit(qt.SIGNAL("LineDoubleClickEvent"), ddict)

class SimpleThread(qt.QThread):
    def __init__(self, function = None, kw = None):
        if kw is None:kw={}
        qt.QThread.__init__(self)
        self._function = function
        self._kw       = kw
        self._result   = None
        self._expandParametersDict = False

    def run(self):
        try:
            if self._expandParametersDict:
                self._result = self._function(**self._kw)
            else:
                self._result = self._function(self._kw)
        except:
            self._result = ("Exception",) + sys.exc_info()


class McaGraphWindow(PlotWindow.PlotWindow):
    def __init__(self, parent=None, backend=None, plugins=False,
                 newplot=False, position=True, control=True, **kw):
        super(McaGraphWindow, self).__init__(parent, backend=backend,
                                       plugins=plugins,
                                       newplot=newplot,
                                       energy=True,
                                       roi=True,
                                       logx=False,
                                       fit=True,
                                       position=position,
                                       control=control,
                                       **kw)
        self.printPreview = PyMcaPrintPreview.PyMcaPrintPreview(modal = 0)

    def printGraph(self):
        pixmap = qt.QPixmap.grabWidget(self.getWidgetHandle())
        self.printPreview.addPixmap(pixmap)
        if self.printPreview.isHidden():
            self.printPreview.show()
        self.printPreview.raise_()

    def _energyIconSignal(self):
        legend = self.getActiveCurve(just_legend=True)
        ddict={}
        ddict['event']  = 'EnergyClicked'
        ddict['active'] = legend
        self.sigPlotSignal.emit(ddict)

    def _fitIconSignal(self):
        legend = self.getActiveCurve(just_legend=True)
        ddict={}
        ddict['event']  = 'FitClicked'
        ddict['active'] = legend
        self.sigPlotSignal.emit(ddict)

    def _saveIconSignal(self):
        legend = self.getActiveCurve(just_legend=True)
        ddict={}
        ddict['event']  = 'SaveClicked'
        ddict['active'] = legend
        self.sigPlotSignal.emit(ddict)

def test(ffile='03novs060sum.mca', cfg=None):
    from PyMca.PyMcaIO import specfilewrapper as specfile
    app = qt.QApplication([])
    app.lastWindowClosed.connect(app.quit)
    sf=specfile.Specfile(ffile)
    scan=sf[-1]
    nMca = scan.nbmca()
    mcadata=scan.mca(nMca)
    y0= numpy.array(mcadata)
    x = numpy.arange(len(y0))*1.0
    demo = McaAdvancedFit()
    #This illustrates how to change the configuration
    #oldConfig = demo.configure()
    #oldConfig['fit']['xmin'] = 123
    #demo.configure(oldConfig)
    if cfg is not None:
        d = ConfigDict.ConfigDict()
        d.read(cfg)
        demo.configure(d)
        d = None
    xmin = demo.mcafit.config['fit']['xmin']
    xmax = demo.mcafit.config['fit']['xmax']
    demo.setData(x,y0,xmin=xmin,xmax=xmax,sourcename=ffile)
    demo.show()
    app.exec_()


def main():
    app = qt.QApplication([])
    form = McaAdvancedFit(top=False)
    form.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    if len(sys.argv) >1:
        ffile = sys.argv[1]
    else:
        ffile = '03novs060sum.mca'
    if len(sys.argv) > 2:
        cfg = sys.argv[2]
    else:
        cfg = None
    if os.path.exists(ffile):
        test(ffile, cfg)
    else:
        main()