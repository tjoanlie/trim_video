

# Copyright (C) 2025 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause

from functools import cache

from PySide6.QtMultimedia import (QAudioBufferOutput, QAudioDevice, QAudioOutput, QMediaDevices,
                                  QMediaFormat, QMediaMetaData, QMediaPlayer)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtCore import QDir, QLocale, QStandardPaths, QTime, Qt, Signal, Slot

from playercontrols import PlayerControls
from videowidget import VideoWidget
import subprocess
import os
from pathlib import Path

MP4 = 'video/mp4'

@cache
def getSupportedMimeTypes():
    result = []
    for f in QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode):
        mime_type = QMediaFormat(f).mimeType()
        result.append(mime_type.name())
    if MP4 not in result:
        result.append(MP4)  # Should always be there when using FFMPEG
    return result


def second2time(in_sec):
    """ convert seconds into HH:MM:SS """
    sec = str(in_sec % 60)
    min = str(in_sec // 60)
    hr  = str(in_sec // 3600)
    if len(sec) == 1:
        sec = '0' + sec
    if len(min) == 1:
        min = '0' + min
    if len(hr) == 1:
        hr = '0' + hr
    return hr + ':' + min + ':' + sec
    

def list2text(in_list):
    """ convert list into simple text """
    out_text = ''
    count = 0
    for val in in_list:
        if out_text == '':
            out_text = second2time(val)
        else:
            if out_text[-2:] == "; ":
                out_text = out_text + second2time(val)
            else:
                out_text = out_text + ' - ' + second2time(val)
        count += 1
        if count % 2 == 0:
            out_text += '; '
    return out_text


class Player(QWidget):

    fullScreenChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lastDir = None
        self.currentVideo = ""
        self.currentVideoDir = ""
        self.timeTrimList = []
        self.m_statusInfo = ""
        self.m_mediaDevices = QMediaDevices()
        self.m_player = QMediaPlayer(self)
        self.m_audioOutput = QAudioOutput(self)
        self.m_player.setAudioOutput(self.m_audioOutput)
        self.m_player.durationChanged.connect(self.durationChanged)
        self.m_player.positionChanged.connect(self.positionChanged)
        self.m_player.metaDataChanged.connect(self.metaDataChanged)
        self.m_player.mediaStatusChanged.connect(self.statusChanged)
        self.m_player.bufferProgressChanged.connect(self.bufferingProgress)
        #self.m_player.hasVideoChanged.connect(self.videoAvailableChanged)
        self.m_player.errorChanged.connect(self.displayErrorMessage)

        self.m_videoWidget = VideoWidget(self)
        available_geometry = self.screen().availableGeometry()
        self.m_videoWidget.setMinimumSize(available_geometry.width() / 2,
                                          available_geometry.height() / 3)
        self.m_player.setVideoOutput(self.m_videoWidget)

        # audio level meter
        self.m_audioBufferOutput = QAudioBufferOutput(self)
        self.m_player.setAudioBufferOutput(self.m_audioBufferOutput)

        # player layout
        layout = QVBoxLayout(self)

        # display
        displayLayout = QHBoxLayout()
        displayLayout.addWidget(self.m_videoWidget, 2)
        layout.addLayout(displayLayout)

        # duration slider and label
        hLayout = QHBoxLayout()

        self.m_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.m_slider.setRange(0, self.m_player.duration())
        self.m_slider.sliderMoved.connect(self.seek)
        hLayout.addWidget(self.m_slider)

        self.m_labelDuration = QLabel()
        self.m_labelDuration.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        hLayout.addWidget(self.m_labelDuration)
        layout.addLayout(hLayout)

        # controls
        controlLayout = QHBoxLayout()
        controlLayout.setContentsMargins(0, 0, 0, 0)

        openButton = QPushButton("Open", self)
        openButton.clicked.connect(self.open)
        controlLayout.addWidget(openButton)
        controlLayout.addStretch(1)

        self.controls = PlayerControls()
        self.controls.setState(self.m_player.playbackState())
        self.controls.setVolume(self.m_audioOutput.volume())
        self.controls.setMuted(self.controls.isMuted())

        self.controls.play.connect(self.m_player.play)
        self.controls.pause.connect(self.m_player.pause)
        self.controls.stop.connect(self.m_player.stop)
        self.controls.previous.connect(self.previousClicked)
        self.controls.backward.connect(self.backwardClicked)
        self.controls.undoTrimEntry.connect(self.undoTrimEntryClicked)
        self.controls.startTrim.connect(self.startTrimClicked)
        self.controls.endTrim.connect(self.endTrimClicked)
        self.controls.forward.connect(self.forwardClicked)
        self.controls.runTrim.connect(self.runTrimClicked)
        self.controls.changeVolume.connect(self.m_audioOutput.setVolume)
        self.controls.changeMuting.connect(self.m_audioOutput.setMuted)
        self.controls.changeRate.connect(self.m_player.setPlaybackRate)
        self.controls.stop.connect(self.m_videoWidget.update)

        self.m_player.playbackStateChanged.connect(self.controls.setState)
        self.m_audioOutput.volumeChanged.connect(self.controls.setVolume)
        self.m_audioOutput.mutedChanged.connect(self.controls.setMuted)

        controlLayout.addWidget(self.controls)
        controlLayout.addStretch(1)

        layout.addLayout(controlLayout)

        # tracks
        tracksLayout = QGridLayout()

        tracksLayout.addWidget(QLabel("Video File:"), 0, 0)
        self.m_videoFile = QLabel(self.currentVideo)
        tracksLayout.addWidget(self.m_videoFile, 0, 1)

        self.m_trimList = QLabel(self)
        tracksLayout.addWidget(QLabel("Trim List:"), 1, 0)
        tracksLayout.addWidget(self.m_trimList, 1, 1)

        tracksLayout.setColumnStretch(0,1)
        tracksLayout.setColumnStretch(1,9)

        self.m_videoTracks = QComboBox(self)
        self.m_videoTracks.activated.connect(self.selectVideoStream)
        #tracksLayout.addWidget(QLabel("Video Tracks:"), 1, 0)
        #tracksLayout.addWidget(self.m_videoTracks, 1, 1)

        layout.addLayout(tracksLayout)

        if not self.isPlayerAvailable():
            QMessageBox.warning(self, "Service not available",
                                "The QMediaPlayer object does not have a valid service.\n"
                                "Please check the media service plugins are installed.")

            controls.setEnabled(False)
            openButton.setEnabled(False)
            self.m_forwardButton.setEnabled(False)
            self.m_runTrimButton.setEnabled(False)
            self.m_startTrimButton.setEnabled(False)
            self.m_endTrimButton.setEnabled(False)
            self.m_backwardButton.setEnabled(False)
            self.m_undoTrimEntryButton.setEnabled(False)
        self.metaDataChanged()

    def closeEvent(self, event):
        #self.m_audioLevelMeter.closeRequest()
        event.accept()

    @Slot()
    def _updatePitchCompensation(self):
        self.m_pitchCompensationButton.setChecked(self.m_player.pitchCompensation())

    def isPlayerAvailable(self):
        return self.m_player.isAvailable()

    @Slot()
    def open(self):
        fileDialog = QFileDialog(self)
        fileDialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        fileDialog.setWindowTitle("Open Files")
        if (self.lastDir):
            fileDialog.setDirectory(self.lastDir)
        else:
            movieDirs = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.MoviesLocation)
            fileDialog.setDirectory(movieDirs[0] if movieDirs else QDir.homePath())
        fileDialog.setMimeTypeFilters(getSupportedMimeTypes())
        fileDialog.selectMimeTypeFilter(MP4)
        if fileDialog.exec() == QDialog.DialogCode.Accepted:
            fileName = fileDialog.selectedUrls()[0].toString().replace("file://","")
            self.lastDir = fileDialog.directory()
            #fileName = fileDialog.selectedUrls()[0].toString().split('/')
            #self.currentVideo = fileName[len(fileName)-1]
            self.currentVideo = fileName
            self.currentVideoDir = Path(fileDialog.selectedUrls()[0].toString().replace("file://", "")).parent
            self.m_videoFile.setText(self.currentVideo)
            self.openUrl(fileDialog.selectedUrls()[0])

    def openUrl(self, url):
        self.m_player.setSource(url)

    @Slot("qlonglong")
    def durationChanged(self, duration):
        self.m_duration = duration / 1000
        self.m_slider.setMaximum(duration)

    @Slot("qlonglong")
    def positionChanged(self, progress):
        if not self.m_slider.isSliderDown():
            self.m_slider.setValue(progress)
        self.updateDurationInfo(progress / 1000)

    @Slot()
    def metaDataChanged(self):
        metaData = self.m_player.metaData()
        artist = metaData.value(QMediaMetaData.Key.AlbumArtist)
        title = metaData.value(QMediaMetaData.Key.Title)
        trackInfo = QApplication.applicationName()
        if artist and title:
            trackInfo = f"{artist} - {title}"
        elif artist:
            trackInfo = artist
        elif title:
            trackInfo = title
        self.setTrackInfo(trackInfo)


    def trackName(self, metaData, index):
        name = ""
        title = metaData.stringValue(QMediaMetaData.Key.Title)
        lang = metaData.value(QMediaMetaData.Key.Language)
        if not title:
            if lang == QLocale.Language.AnyLanguage:
                name = f"Track {index + 1}"
            else:
                name = QLocale.languageToString(lang)
        else:
            if lang == QLocale.Language.AnyLanguage:
                name = title
            else:
                langName = QLocale.languageToString(lang)
                name = f"{title} - [{langName}]"
        return name

    @Slot()
    def previousClicked(self):
        self.m_player.setPosition(0)

    @Slot()
    def backwardClicked(self):
        current_pos = self.m_player.position()
        self.m_player.setPosition(current_pos-5000)

    @Slot()
    def undoTrimEntryClicked(self):
        self.timeTrimList.pop()
        self.m_trimList.setText(list2text(self.timeTrimList))
        self.controls.m_startTrimButton.setStyleSheet("background-color:grey")
        self.controls.m_endTrimButton.setStyleSheet("background-color:grey")
        if (len(self.timeTrimList)) % 2 == 1:
            self.controls.m_endTrimButton.setStyleSheet("background-color:pink")
            self.controls.m_endTrimButton.setEnabled(True)
            self.controls.m_startTrimButton.setEnabled(False)
        else:
            self.controls.m_startTrimButton.setStyleSheet("background-color:#a7e6d7")
            self.controls.m_startTrimButton.setEnabled(True)
            self.controls.m_endTrimButton.setEnabled(False)

    @Slot()
    def startTrimClicked(self):
        self.timeTrimList.append(self.m_player.position()//1000)
        self.m_trimList.setText(list2text(self.timeTrimList))
        self.controls.m_startTrimButton.setStyleSheet("background-color:grey")
        self.controls.m_endTrimButton.setStyleSheet("background-color:pink")
        self.controls.m_startTrimButton.setEnabled(False)
        self.controls.m_endTrimButton.setEnabled(True)

    @Slot()
    def endTrimClicked(self):
        self.timeTrimList.append(self.m_player.position()//1000)
        self.m_trimList.setText(list2text(self.timeTrimList))
        self.controls.m_startTrimButton.setStyleSheet("background-color:#a7e6d7")
        self.controls.m_endTrimButton.setStyleSheet("background-color:grey")
        self.controls.m_startTrimButton.setEnabled(True)
        self.controls.m_endTrimButton.setEnabled(False)

    @Slot()
    def forwardClicked(self):
        current_pos = self.m_player.position()
        self.m_player.setPosition(current_pos+5000)


    @Slot()
    def runTrimClicked(self):
        if len(self.timeTrimList) % 2 == 1:
            print(f"ERROR - incomplete trim windows")
            # TODO must create a pop up window to show the error
        else:
            self.m_player.stop()
            file_handle = open('join.list', 'w')
            for win in range(len(self.timeTrimList)//2):
                stime = second2time(self.timeTrimList.pop(0))
                etime = second2time(self.timeTrimList.pop(0))
                trim_file = f"trim_window_{win}.mp4"
                cmd_line = f"ffmpeg -i {self.currentVideo} -ss {stime} -to {etime} -c copy {trim_file}"
                file_handle.write(f"file {trim_file}\n")
                os.system(cmd_line)
            file_handle.close()
            file_name_arr = self.currentVideo.split('/')
            file_name = file_name_arr[len(file_name_arr)-1]
            out_file = f"{self.currentVideoDir}/join_{file_name}"
            os.system(f"ffmpeg -f concat -i join.list -c copy {out_file}")
            os.system("rm trim_window_*.mp4")
            self.timeTrimList = []
            self.m_trimList.setText(list2text(self.timeTrimList))


    @Slot(int)
    def seek(self, mseconds):
        self.m_player.setPosition(mseconds)

    @Slot(QMediaPlayer.MediaStatus)
    def statusChanged(self, status):
        self.handleCursor(status)
        # handle status message
        if (status == QMediaPlayer.MediaStatus.NoMedia
                or status == QMediaPlayer.MediaStatus.LoadedMedia):
            self.setStatusInfo("")
        elif status == QMediaPlayer.MediaStatus.LoadingMedia:
            self.setStatusInfo("Loading...")
        elif (status == QMediaPlayer.MediaStatus.BufferingMedia
              or status == QMediaPlayer.MediaStatus.BufferedMedia):
            progress = round(self.m_player.bufferProgress() * 100.0)
            self.setStatusInfo(f"Buffering {progress}%")
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            progress = round(self.m_player.bufferProgress() * 100.0)
            self.setStatusInfo(f"Stalled {progress}%")
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            QApplication.alert(self)
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.displayErrorMessage()

    def handleCursor(self, status):
        if (status == QMediaPlayer.MediaStatus.LoadingMedia
                or status == QMediaPlayer.MediaStatus.BufferingMedia
                or status == QMediaPlayer.MediaStatus.StalledMedia):
            self.setCursor(QCursor(Qt.CursorShape.BusyCursor))
        else:
            self.unsetCursor()

    @Slot("float")
    def bufferingProgress(self, progressV):
        progress = round(progressV * 100.0)
        if self.m_player.mediaStatus() == QMediaPlayer.MediaStatus.StalledMedia:
            self.setStatusInfo(f"Stalled {progress}%")
        else:
            self.setStatusInfo(f"Buffering {progress}%")

    @Slot(bool)
    def videoAvailableChanged(self, available):
        if not available:
            self.m_videoWidget.fullScreenChanged.disconnect(self.m_runTrimButton.setChecked)
            self.m_videoWidget.setFullScreen(False)
        else:
            self.m_videoWidget.fullScreenChanged.connect(self.m_runTrimButton.setChecked)
            if self.m_runTrimButton.isChecked():
                self.m_videoWidget.setFullScreen(True)

    @Slot()
    def selectVideoStream(self):
        stream = self.m_videoTracks.currentData()
        self.m_player.setActiveVideoTrack(stream)

    def setTrackInfo(self, info):
        self.m_trackInfo = info
        title = self.m_trackInfo
        if self.m_statusInfo:
            title += f" | {self.m_statusInfo}"
        self.setWindowTitle(title)

    def setStatusInfo(self, info):
        self.m_statusInfo = info
        title = self.m_trackInfo
        if self.m_statusInfo:
            title += f" | {self.m_statusInfo}"
        self.setWindowTitle(title)

    @Slot()
    def displayErrorMessage(self):
        if self.m_player.error() != QMediaPlayer.Error.NoError:
            self.setStatusInfo(self.m_player.errorString())

    def updateDurationInfo(self, currentInfo):
        tStr = ""
        if currentInfo or self.m_duration:
            currentTime = QTime((currentInfo / 3600) % 60, (currentInfo / 60) % 60,
                                currentInfo % 60, (currentInfo * 1000) % 1000)
            totalTime = QTime((self.m_duration / 3600) % 60, (self.m_duration / 60) % 60,
                              self.m_duration % 60, (self.m_duration * 1000) % 1000)
            format = "hh:mm:ss" if self.m_duration > 3600 else "mm:ss"
            tStr = currentTime.toString(format) + " / " + totalTime.toString(format)
        self.m_labelDuration.setText(tStr)

    @Slot()
    def updateAudioDevices(self):
        self.m_audioOutputCombo.clear()

        self.m_audioOutputCombo.addItem("Default", QAudioDevice())
        for deviceInfo in QMediaDevices.audioOutputs():
            self.m_audioOutputCombo.addItem(deviceInfo.description(), deviceInfo)

    @Slot(int)
    def audioOutputChanged(self, index):
        device = self.m_audioOutputCombo.itemData(index)
        self.m_player.audioOutput().setDevice(device)

