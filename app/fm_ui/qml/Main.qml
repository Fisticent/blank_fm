import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "components"

ApplicationWindow {
    id: win
    visible: true
    width: 980
    height: 680
    minimumWidth: 820
    minimumHeight: 560
    color: Colors.bg
    title: app.itemGid > 0 ? ("Dofus FM " + app.appVersion + " - " + app.itemName) : ("Dofus FM " + app.appVersion)
    property int mainTab: 0

    onClosing: function(close) {
        close.accepted = true
        overlayHud.visible = false
        overlayHud.close()
        Qt.callLater(function() { app.quitApp() })
    }

    Connections {
        target: app
        function onRequestShow() {
            win.show()
            win.raise()
            win.requestActivate()
        }
    }

    OverlayHud {
        id: overlayHud
    }

    FileDialog {
        id: replayDialog
        title: "Rejouer une session FM"
        nameFilters: ["Journaux JSONL (*.jsonl)"]
        fileMode: FileDialog.OpenFile
        currentFolder: capturesDir
        onAccepted: app.startReplay(selectedFile.toString())
    }

    Rectangle {
        id: body
        anchors.fill: parent
        color: Colors.bg

        Rectangle {
            id: updateBanner
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: (app.updateAvailable || app.updateBusy) ? 48 : 0
            visible: height > 0
            clip: true
            color: Colors.primary
            Row {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10
                Text {
                    text: app.updateMessage
                    color: Colors.text_on_accent
                    font.family: Colors.font_family
                    font.pixelSize: Colors.font_size_ui
                    font.bold: true
                    elide: Text.ElideRight
                    width: Math.max(80, parent.width - 170)
                    anchors.verticalCenter: parent.verticalCenter
                }
                ThemedButton {
                    label: app.updateBusy ? "Patiente…" : "Mettre a jour"
                    enabled: !app.updateBusy && app.updateAvailable
                    accent: true
                    onClicked: app.applyUpdate()
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        Rectangle {
            id: npcapBanner
            anchors.top: updateBanner.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: app.npcapInstalled ? 0 : 48
            visible: height > 0
            clip: true
            color: Colors.warning
            Row {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10
                Text {
                    text: app.npcapMessage
                    color: Colors.text_on_accent
                    font.family: Colors.font_family
                    font.pixelSize: Colors.font_size_ui
                    font.bold: true
                    elide: Text.ElideRight
                    width: Math.max(80, parent.width - 170)
                    anchors.verticalCenter: parent.verticalCenter
                }
                ThemedButton {
                    label: app.npcapBusy ? "Telechargement…" : "Installer Npcap"
                    enabled: !app.npcapBusy
                    accent: true
                    onClicked: app.installNpcap()
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        Row {
            id: tabRow
            anchors.top: npcapBanner.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.topMargin: 10
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            height: 32
            spacing: 8

            ThemedButton {
                label: "Forge"
                accent: win.mainTab === 0
                onClicked: win.mainTab = 0
            }
            ThemedButton {
                label: "Objets"
                accent: win.mainTab === 1
                onClicked: win.mainTab = 1
            }
            ThemedButton {
                label: "Runes"
                accent: win.mainTab === 2
                onClicked: win.mainTab = 2
            }
            ThemedButton {
                label: "Paramètres"
                accent: win.mainTab === 3
                onClicked: win.mainTab = 3
            }
            ThemedButton {
                label: "Journal"
                accent: win.mainTab === 4
                onClicked: win.mainTab = 4
            }
        }

        Item {
            id: forgePage
            visible: win.mainTab === 0
            anchors.top: tabRow.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: btnRow.top
            anchors.topMargin: 8
            anchors.bottomMargin: 8

            Column {
                id: leftCol
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.leftMargin: 12
                width: 340
                spacing: 10

                SectionCard {
                    id: itemCard
                    width: parent.width
                    height: 108
                    title: "ITEM"

                    Row {
                        anchors.fill: parent
                        spacing: 12

                        Rectangle {
                            width: 64; height: 64
                            radius: Colors.radius_control
                            color: Colors.bg_elevated
                            border.width: 1
                            border.color: Colors.separator
                            Image {
                                id: iconImg
                                anchors.fill: parent
                                anchors.margins: 4
                                source: app.itemIcon
                                fillMode: Image.PreserveAspectFit
                            }
                            Text {
                                visible: iconImg.status !== Image.Ready
                                anchors.centerIn: parent
                                text: app.itemGid > 0 ? app.itemName.charAt(0).toUpperCase() : "?"
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: 28
                                font.bold: true
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                text: app.itemName
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_heading
                                font.bold: true
                                elide: Text.ElideRight
                                width: 210
                            }
                            Text {
                                text: app.itemGid > 0
                                      ? ("GID " + app.itemGid + "  •  UID " + app.itemUid)
                                      : app.statusText
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                                width: 210
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                visible: app.jetPct >= 0
                                text: "Jet global : " + app.jetPct.toFixed(1) + "%"
                                color: app.jetPct >= Colors.JET_GREEN ? Colors.success
                                     : app.jetPct >= Colors.JET_YELLOW ? Colors.warning
                                     : Colors.danger
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                            }
                        }
                    }
                }

                SectionCard {
                    id: statsCard
                    width: parent.width
                    height: Math.max(200, leftCol.height - 118)
                    title: "STATS"

                    ListView {
                        id: statsList
                        anchors.fill: parent
                        model: app.statsModel
                        spacing: 4
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: StatChip {
                            width: statsList.width
                            statName: modelData.name
                            statColor: modelData.color
                            statValue: modelData.value
                            statPct: modelData.pct
                            statIcon: modelData.icon || ""
                            runeCount: modelData.runes || 0
                            costText: modelData.cost || ""
                            negative: modelData.negative
                        }
                        Text {
                            visible: statsList.count === 0
                            anchors.centerIn: parent
                            text: "Aucune stat pour l'instant"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                        }
                    }
                }
            }

            Column {
                id: rightCol
                anchors.top: parent.top
                anchors.left: leftCol.right
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: 10
                anchors.rightMargin: 12
                spacing: 10

                Row {
                    width: parent.width
                    height: 120
                    spacing: 10

                    SectionCard {
                        width: (parent.width - 20) / 3
                        height: parent.height
                        title: "PUITS"
                        Column {
                            anchors.fill: parent
                            spacing: 4
                            Text {
                                text: app.puit.toFixed(1)
                                color: Colors.primary_bright
                                font.family: Colors.font_family
                                font.pixelSize: 26
                                font.bold: true
                            }
                            Text {
                                text: "Δ " + app.puitDeltaTotal.toFixed(1)
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                            Text {
                                text: "reliquat " + app.reliquatCumul.toFixed(1)
                                color: Colors.warning
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                        }
                    }

                    SectionCard {
                        width: (parent.width - 20) / 3
                        height: parent.height
                        title: "COÛT RUNES"
                        Column {
                            anchors.fill: parent
                            spacing: 4
                            KamaAmount {
                                amount: app.costFormatted
                                iconSize: 18
                                pixelSize: 20
                                bold: true
                                width: parent.width
                            }
                            Text {
                                text: app.poses + " pose(s) de rune"
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                        }
                    }

                    SectionCard {
                        width: (parent.width - 20) / 3
                        height: parent.height
                        title: "TEMPS"
                        Column {
                            anchors.fill: parent
                            spacing: 4
                            Text {
                                text: "Session " + app.sessionDuration + (app.timerPaused ? "  pause" : "")
                                color: app.timerPaused ? Colors.text_muted : Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_heading
                                font.bold: true
                            }
                            Text {
                                text: "Sur cet item : " + app.itemDuration
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                            }
                            Text {
                                visible: app.exoAvgTimeFormatted.length > 0
                                text: "Exo " + app.exoAvgTimeFormatted
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                            }
                        }
                    }
                }

                SectionCard {
                    id: issuesCard
                    width: parent.width
                    height: 64
                    title: "TYPE DE SUCCÈS"
                    Row {
                        anchors.fill: parent
                        spacing: 20
                        Row {
                            spacing: 6
                            Text {
                                text: "Succès"
                                color: Colors.success
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                            }
                            Text {
                                text: "" + app.scCount
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                            }
                        }
                        Row {
                            spacing: 6
                            Text {
                                text: "Neutre"
                                color: Colors.primary_bright
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                            }
                            Text {
                                text: "" + app.snCount
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                            }
                        }
                        Row {
                            spacing: 6
                            Text {
                                text: "Échec"
                                color: Colors.danger
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                            }
                            Text {
                                text: "" + app.ecCount
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                            }
                        }
                    }
                }

                SectionCard {
                    id: exoCard
                    width: parent.width
                    height: Math.max(72, exoFlow.implicitHeight + 52)
                    clipContent: false
                    title: "TENTATIVES D'EXO"
                    Flow {
                        id: exoFlow
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: app.exoAttemptsModel
                            Row {
                                spacing: 6
                                height: 22
                                Image {
                                    width: (modelData.icon || "") !== "" ? 14 : 0
                                    height: 14
                                    visible: width > 0
                                    source: modelData.icon || ""
                                    fillMode: Image.PreserveAspectFit
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Text {
                                    text: modelData.label
                                    color: Colors.text_muted
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    font.bold: true
                                    wrapMode: Text.NoWrap
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Text {
                                    text: "" + modelData.attempts
                                    color: modelData.attempts > 0 ? modelData.color : Colors.text_muted
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Text {
                                    visible: modelData.landed > 0
                                    text: "(" + modelData.landed + ")"
                                    color: Colors.success
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                    font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                KamaAmount {
                                    amount: modelData.costText || ""
                                    iconSize: 12
                                    pixelSize: Colors.font_size_secondary
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                KamaAmount {
                                    amount: modelData.costPerText || ""
                                    suffix: "/t"
                                    iconSize: 12
                                    pixelSize: Colors.font_size_secondary
                                    textColor: Colors.text_muted
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    }
                }

                SectionCard {
                    id: histCard
                    width: parent.width
                    height: Math.max(80, parent.height - 214 - exoCard.height)
                    title: "HISTORIQUE"

                    ListView {
                        id: histList
                        anchors.fill: parent
                        model: app.historyModel
                        spacing: 2
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: Row {
                            width: histList.width
                            spacing: 8
                            Text {
                                text: modelData.num + "."
                                width: 26
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                            Text {
                                text: modelData.rune
                                width: 110
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                                elide: Text.ElideRight
                            }
                            Text {
                                text: modelData.outcomeLabel || modelData.outcome
                                width: 56
                                color: modelData.outcome === "SC" ? Colors.success
                                     : modelData.outcome === "SN" ? Colors.primary_bright
                                     : modelData.outcome === "EC" ? Colors.danger : Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                                font.bold: true
                            }
                            Text {
                                text: Number(modelData.puit).toFixed(1)
                                width: 46
                                color: Colors.primary_bright
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                            KamaAmount {
                                amount: modelData.cost
                                iconSize: 12
                                pixelSize: Colors.font_size_secondary
                                width: 90
                            }
                            Text {
                                text: modelData.effects
                                width: Math.max(40, histList.width - 340)
                                color: Colors.text_muted
                                elide: Text.ElideRight
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                        }
                        Text {
                            visible: histList.count === 0
                            anchors.centerIn: parent
                            text: "Aucune pose encore"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                        }
                    }
                }
            }
        }

        Item {
            id: recentPage
            visible: win.mainTab === 1
            anchors.top: tabRow.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: btnRow.top
            anchors.margins: 12
            anchors.topMargin: 8
            anchors.bottomMargin: 8

            SectionCard {
                anchors.fill: parent
                title: app.historyLimit + " DERNIERS OBJETS FM"

                ListView {
                    id: recentList
                    anchors.fill: parent
                    model: app.recentItemsModel
                    spacing: 8
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Rectangle {
                        id: histRow
                        width: recentList.width
                        height: (modelData.exoSummary || "") !== "" ? 104 : 88
                        radius: Colors.radius_control
                        color: histClick.containsMouse ? Colors.secondary_hover : Colors.bg_elevated
                        border.width: 1
                        border.color: modelData.current ? Colors.primary : Colors.separator

                        MouseArea {
                            id: histClick
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                app.openHistoryDetail(index)
                                historyPopup.open()
                            }
                        }

                        Row {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 12

                            Rectangle {
                                width: 64; height: 64
                                radius: Colors.radius_control
                                color: Colors.bg
                                border.width: 1
                                border.color: Colors.separator
                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    source: modelData.icon || ""
                                    fillMode: Image.PreserveAspectFit
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3
                                width: Math.max(160, recentList.width * 0.38)

                                Row {
                                    spacing: 8
                                    Text {
                                        text: modelData.name
                                        color: Colors.text
                                        font.family: Colors.font_family
                                        font.pixelSize: Colors.font_size_heading
                                        font.bold: true
                                        elide: Text.ElideRight
                                        width: Math.max(80, recentList.width * 0.28)
                                    }
                                    Text {
                                        visible: modelData.current
                                        text: "en cours"
                                        color: Colors.primary_bright
                                        font.family: Colors.font_family
                                        font.pixelSize: Colors.font_size_secondary
                                        font.bold: true
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                                Text {
                                    text: "GID " + modelData.gid + "  •  UID " + modelData.uid
                                    color: Colors.text_muted
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                }
                                Text {
                                    visible: Number(modelData.jet) >= 0
                                    text: "Jet " + Number(modelData.jet).toFixed(1) + "%"
                                    color: Number(modelData.jet) >= Colors.JET_GREEN ? Colors.success
                                         : Number(modelData.jet) >= Colors.JET_YELLOW ? Colors.warning
                                         : Colors.danger
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    font.bold: true
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 4
                                width: 140
                                Text {
                                    text: modelData.poses + " pose(s)"
                                    color: Colors.text
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                }
                                KamaAmount {
                                    amount: modelData.cost || ""
                                    iconSize: 12
                                    pixelSize: Colors.font_size_ui
                                    bold: true
                                }
                                Text {
                                    text: "Puits " + Number(modelData.puit).toFixed(1)
                                    color: Colors.primary_bright
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                }
                                Text {
                                    visible: (modelData.exoSummary || "") !== ""
                                    text: "Exo  " + (modelData.exoSummary || "")
                                    color: Colors.warning
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3
                                width: 100
                                Text {
                                    text: "Succès  " + modelData.sc
                                    color: Colors.success
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                    font.bold: true
                                }
                                Text {
                                    text: "Neutre  " + modelData.sn
                                    color: Colors.primary_bright
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                    font.bold: true
                                }
                                Text {
                                    text: "Échec  " + modelData.ec
                                    color: Colors.danger
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                    font.bold: true
                                }
                            }

                            ThemedButton {
                                property string imgLabel: "Image"
                                label: imgLabel
                                tooltip: "Copier une carte du FM (jet, runes, exo, prix)"
                                anchors.verticalCenter: parent.verticalCenter
                                Timer {
                                    id: imgCopied
                                    interval: 1800
                                    onTriggered: parent.imgLabel = "Image"
                                }
                                onClicked: {
                                    if (app.copyShareImage(index)) {
                                        imgLabel = "Copiée"
                                        imgCopied.restart()
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        visible: recentList.count === 0
                        anchors.centerIn: parent
                        text: "Aucun objet FM pour l'instant"
                        color: Colors.text_muted
                        font.family: Colors.font_family
                        font.pixelSize: Colors.font_size_secondary
                    }
                }
            }

            Popup {
                id: historyPopup
                parent: Overlay.overlay
                anchors.centerIn: parent
                width: Math.min(560, win.width - 36)
                height: Math.min(600, win.height - 36)
                modal: true
                focus: true
                padding: 0
                closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                onOpened: historyPopup.imgLabel = "Image"
                background: Rectangle {
                    color: Colors.bg_card
                    radius: Colors.radius_card
                    border.width: 1
                    border.color: Colors.separator
                }

                readonly property var d: app.historyDetail
                property string imgLabel: "Image"

                Column {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    Row {
                        width: parent.width
                        spacing: 12
                        height: 64

                        Rectangle {
                            width: 64; height: 64
                            radius: Colors.radius_control
                            color: Colors.bg
                            border.width: 1
                            border.color: Colors.separator
                            Image {
                                anchors.fill: parent
                                anchors.margins: 4
                                source: historyPopup.d.icon || ""
                                fillMode: Image.PreserveAspectFit
                            }
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            width: Math.max(120, historyPopup.width - 220)
                            Text {
                                text: historyPopup.d.name || ""
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_heading
                                font.bold: true
                                elide: Text.ElideRight
                                width: parent.width
                            }
                            Text {
                                text: "GID " + (historyPopup.d.gid || 0) + "  •  UID " + (historyPopup.d.uid || 0)
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                            Text {
                                visible: Number(historyPopup.d.jet) >= 0
                                text: "Jet " + Number(historyPopup.d.jet).toFixed(1) + "%"
                                color: Number(historyPopup.d.jet) >= Colors.JET_GREEN ? Colors.success
                                     : Number(historyPopup.d.jet) >= Colors.JET_YELLOW ? Colors.warning
                                     : Colors.danger
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                            }
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            ThemedButton {
                                label: historyPopup.imgLabel
                                tooltip: "Copier la carte image"
                                onClicked: {
                                    if (app.copyHistoryDetailImage()) {
                                        historyPopup.imgLabel = "Copiée"
                                        histImgReset.restart()
                                    }
                                }
                            }
                            ThemedButton {
                                label: "Fermer"
                                onClicked: historyPopup.close()
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 16
                        Text {
                            text: (historyPopup.d.poses || 0) + " pose(s)"
                            color: Colors.text
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_ui
                        }
                        KamaAmount {
                            amount: historyPopup.d.cost || ""
                            iconSize: 12
                            pixelSize: Colors.font_size_ui
                            bold: true
                        }
                        Text {
                            visible: (historyPopup.d.avg || "") !== ""
                            text: "moy. " + (historyPopup.d.avg || "")
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Succès " + (historyPopup.d.sc || 0)
                            color: Colors.success
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                        Text {
                            text: "Neutre " + (historyPopup.d.sn || 0)
                            color: Colors.primary_bright
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                        Text {
                            text: "Échec " + (historyPopup.d.ec || 0)
                            color: Colors.danger
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                    }
                    Text {
                        visible: (historyPopup.d.exoSummary || "") !== ""
                        text: "Exo  " + (historyPopup.d.exoSummary || "")
                        color: Colors.warning
                        font.family: Colors.font_family
                        font.pixelSize: Colors.font_size_secondary
                    }

                    Row {
                        width: parent.width
                        height: parent.height - 160
                        spacing: 12

                        Column {
                            width: Math.floor((parent.width - 12) * 0.55)
                            height: parent.height
                            spacing: 6
                            Text {
                                text: "JET"
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                                font.bold: true
                            }
                            ListView {
                                width: parent.width
                                height: parent.height - 22
                                clip: true
                                model: historyPopup.d.stats || []
                                spacing: 3
                                boundsBehavior: Flickable.StopAtBounds
                                delegate: StatChip {
                                    width: ListView.view.width
                                    statName: modelData.name
                                    statColor: modelData.over ? "#d4b45a" : (modelData.exo ? "#5a9fd4" : modelData.color)
                                    statValue: modelData.value
                                    statPct: modelData.pct || ""
                                    statIcon: modelData.icon || ""
                                    negative: modelData.negative
                                }
                                Text {
                                    visible: parent.count === 0
                                    anchors.centerIn: parent
                                    text: "Pas de jet enregistre"
                                    color: Colors.text_muted
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                }
                            }
                        }

                        Column {
                            width: Math.floor((parent.width - 12) * 0.45)
                            height: parent.height
                            spacing: 6
                            Text {
                                text: "RUNES"
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                                font.bold: true
                            }
                            ListView {
                                width: parent.width
                                height: parent.height - 22
                                clip: true
                                model: historyPopup.d.runes || []
                                spacing: 4
                                boundsBehavior: Flickable.StopAtBounds
                                delegate: Row {
                                    width: ListView.view.width
                                    height: 22
                                    spacing: 6
                                    Image {
                                        visible: (modelData.icon || "") !== ""
                                        width: 18; height: 18
                                        source: modelData.icon || ""
                                        fillMode: Image.PreserveAspectFit
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Text {
                                        width: Math.max(40, parent.width - 130)
                                        text: modelData.name
                                        color: Colors.text
                                        font.family: Colors.font_family
                                        font.pixelSize: Colors.font_size_ui
                                        elide: Text.ElideRight
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Text {
                                        width: 36
                                        text: "×" + modelData.count
                                        color: Colors.text
                                        font.family: Colors.font_family
                                        font.pixelSize: Colors.font_size_ui
                                        font.bold: true
                                        horizontalAlignment: Text.AlignRight
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    KamaAmount {
                                        amount: modelData.cost || ""
                                        iconSize: 11
                                        pixelSize: Colors.font_size_secondary
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                                Text {
                                    visible: parent.count === 0
                                    anchors.centerIn: parent
                                    text: "Pas de runes enregistrees"
                                    color: Colors.text_muted
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                }
                            }
                        }
                    }
                }

                Timer {
                    id: histImgReset
                    interval: 1800
                    onTriggered: historyPopup.imgLabel = "Image"
                }
            }
        }

        Item {
            id: runesPage
            visible: win.mainTab === 2
            anchors.top: tabRow.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: btnRow.top
            anchors.margins: 12
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            readonly property int colPad: 12
            readonly property int colGap: 8
            readonly property int colIcon: 36
            readonly property int colVal: 44
            readonly property int colPoids: 52
            readonly property int colPrix: 140
            function colInner() {
                return Math.max(200, runesList.width)
            }
            function colFlex() {
                // pad, icon, name, stat, val, poids, prix, pad → 8 enfants, 7 gouttières
                var fixed = colPad * 2 + colIcon + colVal + colPoids + colPrix + colGap * 7
                return Math.max(80, colInner() - fixed)
            }
            function colName() {
                return Math.floor(colFlex() * 0.56)
            }
            function colStat() {
                return Math.max(70, colFlex() - colName())
            }

            SectionCard {
                anchors.fill: parent
                title: "PRIX MOYEN DES RUNES  ·  " + app.runesCatalogCount + " rune(s)"
                       + (app.pricesUpdatedLabel.length
                          ? "  ·  maj " + app.pricesUpdatedLabel
                          : "")

                Column {
                    anchors.fill: parent
                    spacing: 8

                    Row {
                        width: parent.width
                        height: 30
                        spacing: 8

                        Rectangle {
                            width: Math.max(160, parent.width - horizonRow.width - 8)
                            height: parent.height
                            radius: Colors.radius_control
                            color: Colors.bg_elevated
                            border.width: 1
                            border.color: Colors.separator
                            TextInput {
                                id: runeSearch
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                verticalAlignment: Text.AlignVCenter
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                clip: true
                                onTextChanged: app.setRuneFilter(text)
                            }
                            Text {
                                visible: runeSearch.text.length === 0 && !runeSearch.activeFocus
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 10
                                text: "Filtrer par nom, stat ou GID"
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                            }
                        }

                        Row {
                            id: horizonRow
                            spacing: 4
                            height: parent.height
                            ThemedButton {
                                label: "Session"
                                accent: app.priceHorizon === "session"
                                anchors.verticalCenter: parent.verticalCenter
                                onClicked: app.setPriceHorizon("session")
                            }
                            ThemedButton {
                                label: "7j"
                                accent: app.priceHorizon === "7d"
                                anchors.verticalCenter: parent.verticalCenter
                                onClicked: app.setPriceHorizon("7d")
                            }
                            ThemedButton {
                                label: "30j"
                                accent: app.priceHorizon === "30d"
                                anchors.verticalCenter: parent.verticalCenter
                                onClicked: app.setPriceHorizon("30d")
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        height: 20
                        spacing: 8

                        Rectangle {
                            width: 16
                            height: 16
                            radius: 8
                            anchors.verticalCenter: parent.verticalCenter
                            color: app.pricesUpToDate ? Colors.success : Colors.warning
                            visible: app.pricesUpdatedLabel.length > 0
                            Text {
                                anchors.centerIn: parent
                                text: app.pricesUpToDate ? "✓" : "!"
                                color: Colors.text_on_accent
                                font.family: Colors.font_family
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: app.pricesUpdatedLabel.length > 0
                            text: app.pricesUpToDate
                                  ? "Prix à jour"
                                  : "Prix pas à jour — déco/reco ton personnage pour les mettre à jour"
                            color: app.pricesUpToDate ? Colors.success : Colors.warning
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: app.pricesUpdatedLabel.length === 0
                            text: "Aucun prix capté — déco/reco ton personnage pour les récupérer"
                            color: Colors.warning
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                    }

                    Row {
                        width: parent.width
                        height: 18
                        spacing: runesPage.colGap
                        Item { width: runesPage.colPad; height: 1 }
                        Item { width: runesPage.colIcon; height: 1 }
                        Text {
                            width: runesPage.colName()
                            text: "Rune"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                        Text {
                            width: runesPage.colStat()
                            text: "Stat"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                        Text {
                            width: runesPage.colVal
                            text: "Val."
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                            horizontalAlignment: Text.AlignRight
                        }
                        Text {
                            width: runesPage.colPoids
                            text: "Poids"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                            horizontalAlignment: Text.AlignRight
                        }
                        Text {
                            width: runesPage.colPrix
                            text: "Prix moyen"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                            horizontalAlignment: Text.AlignRight
                        }
                        Item { width: runesPage.colPad; height: 1 }
                    }

                    ListView {
                        id: runesList
                        width: parent.width
                        // 56 = recherche/horizon (30) + en-tete colonnes (18) + 2
                        // gouttieres (8+8) ; +28 = ligne de statut prix (20) + sa
                        // gouttiere (8) ajoutee au-dessus de l'en-tete.
                        height: Math.max(80, parent.height - 84)
                        model: app.runesCatalogModel
                        spacing: 4
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: Rectangle {
                            width: runesList.width
                            height: 52
                            radius: Colors.radius_control
                            color: Colors.bg_elevated
                            border.width: 1
                            border.color: Colors.separator

                            Row {
                                width: parent.width
                                height: parent.height
                                spacing: runesPage.colGap

                                Item { width: runesPage.colPad; height: 1 }

                                Image {
                                    width: runesPage.colIcon
                                    height: runesPage.colIcon
                                    anchors.verticalCenter: parent.verticalCenter
                                    source: modelData.icon || ""
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                    cache: true
                                }

                                Text {
                                    width: runesPage.colName()
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.name
                                    color: Colors.text
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: runesPage.colStat()
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.stat
                                    color: Colors.text_muted
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: runesPage.colVal
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.value
                                    color: Colors.text
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    horizontalAlignment: Text.AlignRight
                                }
                                Text {
                                    width: runesPage.colPoids
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.weight
                                    color: Colors.primary_bright
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    horizontalAlignment: Text.AlignRight
                                }
                                Item {
                                    width: runesPage.colPrix
                                    height: parent.height
                                    Column {
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 1
                                        KamaAmount {
                                            anchors.right: parent.right
                                            amount: modelData.price || ""
                                            iconSize: 13
                                            pixelSize: Colors.font_size_ui
                                            bold: true
                                        }
                                        Text {
                                            visible: (modelData.priceDeltaLabel || "") !== ""
                                            anchors.right: parent.right
                                            text: modelData.priceDeltaLabel || ""
                                            color: modelData.priceDeltaDir === "up" ? Colors.success
                                                 : modelData.priceDeltaDir === "down" ? Colors.danger
                                                 : Colors.text_muted
                                            font.family: Colors.font_family
                                            font.pixelSize: Colors.font_size_secondary
                                            font.bold: modelData.priceDeltaDir === "up" || modelData.priceDeltaDir === "down"
                                        }
                                    }
                                }
                                Item { width: runesPage.colPad; height: 1 }
                            }
                        }
                        Text {
                            visible: runesList.count === 0
                            anchors.centerIn: parent
                            text: "Aucune rune ne correspond"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                        }
                    }
                }
            }
        }

        Item {
            id: settingsPage
            visible: win.mainTab === 3
            anchors.top: tabRow.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: btnRow.top
            anchors.margins: 12
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            property int statPickIndex: 0

            function currentStatEid() {
                var rows = app.statChoicesModel
                if (settingsPage.statPickIndex < 0 || settingsPage.statPickIndex >= rows.length)
                    return 0
                return rows[settingsPage.statPickIndex].eid
            }

            function currentStatName() {
                var rows = app.statChoicesModel
                if (!rows || rows.length === 0)
                    return "Aucune caractéristique"
                if (settingsPage.statPickIndex < 0 || settingsPage.statPickIndex >= rows.length)
                    return "Choisir une caractéristique"
                return rows[settingsPage.statPickIndex].name
            }

            Flickable {
                id: settingsFlick
                anchors.fill: parent
                clip: true
                contentWidth: width
                contentHeight: settingsCol.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                Column {
                    id: settingsCol
                    width: settingsFlick.width
                    spacing: 10

                SectionCard {
                    width: parent.width
                    autoHeight: true
                    title: "PENDANT LA FM"

                    Column {
                        width: parent.width
                        spacing: 10

                        SettingsRow {
                            label: "Overlay"
                            hint: "Coût, temps, tentatives d'exo"
                            ThemedSwitch {
                                checked: app.overlayEnabled
                                onClicked: app.setOverlayEnabled(!app.overlayEnabled)
                            }
                        }
                        SettingsRow {
                            label: "Alerte stock runes"
                            hint: "Si une rune passe sous " + app.runeLowQty
                            ThemedSwitch {
                                checked: app.overlayLowRunesEnabled
                                onClicked: app.setOverlayLowRunesEnabled(!app.overlayLowRunesEnabled)
                            }
                        }
                        SettingsRow {
                            label: "Retracter l'overlay en pause"
                            hint: "Passe en pastille minimale tant que la FM est en pause"
                            ThemedSwitch {
                                checked: app.overlayCollapseOnPauseEnabled
                                onClicked: app.setOverlayCollapseOnPauseEnabled(!app.overlayCollapseOnPauseEnabled)
                            }
                        }
                        Row {
                            width: parent.width
                            spacing: 10
                            height: 28
                            Slider {
                                id: runeLowSlider
                                width: parent.width - 40
                                from: 10
                                to: 100
                                stepSize: 10
                                snapMode: Slider.SnapAlways
                                value: app.runeLowQty
                                onMoved: app.setRuneLowQty(Math.round(value))
                                background: Rectangle {
                                    x: runeLowSlider.leftPadding
                                    y: runeLowSlider.topPadding + runeLowSlider.availableHeight / 2 - height / 2
                                    implicitWidth: 160
                                    implicitHeight: 4
                                    width: runeLowSlider.availableWidth
                                    height: implicitHeight
                                    radius: 2
                                    color: Colors.secondary
                                    Rectangle {
                                        width: runeLowSlider.visualPosition * parent.width
                                        height: parent.height
                                        color: Colors.primary
                                        radius: 2
                                    }
                                }
                                handle: Rectangle {
                                    x: runeLowSlider.leftPadding + runeLowSlider.visualPosition * (runeLowSlider.availableWidth - width)
                                    y: runeLowSlider.topPadding + runeLowSlider.availableHeight / 2 - height / 2
                                    implicitWidth: 16
                                    implicitHeight: 16
                                    radius: 8
                                    color: Colors.text
                                    border.width: 1
                                    border.color: Colors.primary_bright
                                }
                            }
                            Text {
                                width: 30
                                anchors.verticalCenter: parent.verticalCenter
                                text: "" + app.runeLowQty
                                color: Colors.text
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_ui
                                font.bold: true
                                horizontalAlignment: Text.AlignRight
                            }
                        }
                        SettingsRow {
                            label: "Son exo"
                            ThemedSwitch {
                                checked: app.soundExoEnabled
                                onClicked: app.setSoundExoEnabled(!app.soundExoEnabled)
                            }
                        }
                        SettingsRow {
                            label: "Son perte"
                            ThemedSwitch {
                                checked: app.soundPerteEnabled
                                onClicked: app.setSoundPerteEnabled(!app.soundPerteEnabled)
                            }
                        }
                        SettingsRow {
                            label: "Pleurs (exo raté)"
                            ThemedSwitch {
                                checked: app.soundExoFailEnabled
                                onClicked: app.setSoundExoFailEnabled(!app.soundExoFailEnabled)
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: Colors.separator
                        }

                        Text {
                            width: parent.width
                            text: "Caractéristiques surveillées"
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }

                        Row {
                            width: parent.width
                            spacing: 8
                            height: 30

                            Rectangle {
                                id: statPickBtn
                                width: Math.min(260, parent.width * 0.42)
                                height: 30
                                radius: Colors.radius_control
                                color: Colors.bg_elevated
                                border.width: 1
                                border.color: Colors.separator
                                Text {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    text: settingsPage.currentStatName()
                                    color: Colors.text
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_ui
                                    elide: Text.ElideRight
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: statPopup.open()
                                }
                            }

                            ThemedButton {
                                label: "Ajouter exo"
                                accent: true
                                onClicked: app.addSoundRule(settingsPage.currentStatEid(), "exo")
                            }
                            ThemedButton {
                                label: "Ajouter perte"
                                onClicked: app.addSoundRule(settingsPage.currentStatEid(), "perte")
                            }
                        }

                        ListView {
                            id: rulesList
                            width: parent.width
                            height: Math.min(188, Math.max(80, contentHeight))
                            model: app.soundRulesModel
                            spacing: 6
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            delegate: Rectangle {
                                width: rulesList.width
                                height: 36
                                radius: Colors.radius_control
                                color: Colors.bg_elevated
                                border.width: 1
                                border.color: Colors.separator

                                Row {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 8
                                    spacing: 12

                                    Text {
                                        width: Math.max(120, parent.width - 250)
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.name
                                        color: Colors.text
                                        font.family: Colors.font_family
                                        font.pixelSize: Colors.font_size_ui
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: 110
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.kindLabel
                                        color: modelData.kind === "exo" ? Colors.success : Colors.danger
                                        font.family: Colors.font_family
                                        font.pixelSize: Colors.font_size_ui
                                        font.bold: true
                                    }
                                    ThemedButton {
                                        label: "Retirer"
                                        anchors.verticalCenter: parent.verticalCenter
                                        onClicked: app.removeSoundRule(modelData.key)
                                    }
                                }
                            }
                            Text {
                                visible: rulesList.count === 0
                                anchors.centerIn: parent
                                text: "Aucune caractéristique dans la liste"
                                color: Colors.text_muted
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                        }
                    }
                }

                SectionCard {
                    width: parent.width
                    autoHeight: true
                    title: "CAPTURE"

                    SettingsRow {
                        label: "Npcap"
                        hint: app.npcapInstalled ? "" : app.npcapMessage
                        Row {
                            spacing: 8
                            Rectangle {
                                implicitWidth: npcapPillText.implicitWidth + 16
                                implicitHeight: 22
                                height: implicitHeight
                                width: implicitWidth
                                radius: 11
                                color: Colors.bg_elevated
                                border.width: 1
                                border.color: app.npcapInstalled ? Colors.success : Colors.warning
                                Text {
                                    id: npcapPillText
                                    anchors.centerIn: parent
                                    text: app.npcapInstalled ? "OK" : "Manquant"
                                    color: app.npcapInstalled ? Colors.success : Colors.warning
                                    font.family: Colors.font_family
                                    font.pixelSize: Colors.font_size_secondary
                                    font.bold: true
                                }
                            }
                            ThemedButton {
                                label: app.npcapInstalled ? "Verifier" : (app.npcapBusy ? "Telechargement…" : "Installer Npcap")
                                enabled: !app.npcapBusy
                                accent: !app.npcapInstalled
                                onClicked: app.npcapInstalled ? app.refreshNpcap() : app.installNpcap()
                            }
                        }
                    }
                }

                SectionCard {
                    width: parent.width
                    autoHeight: true
                    title: "OUTIL"

                    Column {
                        width: parent.width
                        spacing: 8

                        SettingsRow {
                            label: "Historique"
                            hint: "Objets gardes, carte image incluse"
                            Row {
                                spacing: 4
                                ThemedButton {
                                    label: "10"
                                    accent: app.historyLimit === 10
                                    onClicked: app.setHistoryLimit(10)
                                }
                                ThemedButton {
                                    label: "25"
                                    accent: app.historyLimit === 25
                                    onClicked: app.setHistoryLimit(25)
                                }
                                ThemedButton {
                                    label: "50"
                                    accent: app.historyLimit === 50
                                    onClicked: app.setHistoryLimit(50)
                                }
                                ThemedButton {
                                    label: "100"
                                    accent: app.historyLimit === 100
                                    onClicked: app.setHistoryLimit(100)
                                }
                            }
                        }

                        SettingsRow {
                            label: "Version " + app.appVersion
                            hint: app.updateAvailable ? app.updateMessage : "A jour"
                            ThemedButton {
                                label: app.updateAvailable ? (app.updateBusy ? "Patiente…" : "Mettre a jour") : "Verifier"
                                enabled: !app.updateBusy
                                accent: app.updateAvailable
                                onClicked: app.updateAvailable ? app.applyUpdate() : app.checkForUpdate()
                            }
                        }

                        SettingsRow {
                            label: "Protocole"
                            hint: app.protoStatus || "Proto defaut (kfb / kdr / iuj)"
                            ThemedButton {
                                label: "Reapprendre"
                                tooltip: "Recommence a identifier les messages apres un patch Dofus (3 poses)"
                                onClicked: app.relearnProto()
                            }
                        }
                    }
                }
                }
            }

            Popup {
                id: statPopup
                parent: statPickBtn
                y: statPickBtn.height + 4
                x: 0
                width: Math.max(280, statPickBtn.width)
                height: 300
                padding: 6
                modal: true
                focus: true
                closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                background: Rectangle {
                    color: Colors.bg_card
                    border.width: 1
                    border.color: Colors.separator
                    radius: Colors.radius_card
                }

                ListView {
                    anchors.fill: parent
                    model: app.statChoicesModel
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 28
                        color: pickMa.containsMouse ? Colors.secondary_hover : "transparent"
                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 8
                            text: modelData.name
                            color: Colors.text
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_ui
                            elide: Text.ElideRight
                        }
                        MouseArea {
                            id: pickMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                settingsPage.statPickIndex = index
                                statPopup.close()
                            }
                        }
                    }
                }
            }
        }

        Item {
            id: logPage
            visible: win.mainTab === 4
            anchors.top: tabRow.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: btnRow.top
            anchors.margins: 12
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            property string copyLabel: "Copier"
            Timer {
                id: logCopyReset
                interval: 1800
                onTriggered: logPage.copyLabel = "Copier"
            }

            Row {
                id: logToolbar
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 30
                spacing: 8

                ThemedButton {
                    label: logPage.copyLabel
                    accent: true
                    tooltip: "Copie le rapport (version, proto, npcap + logs) dans le presse-papiers"
                    onClicked: {
                        app.copyLog()
                        logPage.copyLabel = "Copié"
                        logCopyReset.restart()
                    }
                }
                ThemedButton {
                    label: "Vider"
                    tooltip: "Efface l'affichage, le fichier dofus_fm.log est conserve"
                    onClicked: app.clearLog()
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: app.protoStatus || ""
                    color: Colors.text_muted
                    font.family: Colors.font_family
                    font.pixelSize: Colors.font_size_secondary
                    elide: Text.ElideRight
                    width: Math.max(80, logToolbar.width - 220)
                }
            }

            Rectangle {
                anchors.top: logToolbar.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.topMargin: 8
                radius: Colors.radius_card
                color: Colors.bg_elevated
                border.width: 1
                border.color: Colors.separator
                clip: true

                Flickable {
                    id: logFlick
                    anchors.fill: parent
                    anchors.margins: 10
                    clip: true
                    contentWidth: width
                    contentHeight: logBody.height
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    Text {
                        id: logBody
                        width: logFlick.width
                        text: app.logText.length > 0
                              ? app.logText
                              : "Les messages de l'outil s'affichent ici.\nCopier envoie un rapport (version, Npcap, proto + logs)."
                        color: app.logText.length > 0 ? Colors.text : Colors.text_muted
                        font.family: "Consolas"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                        onTextChanged: Qt.callLater(function() {
                            if (logFlick.contentHeight > logFlick.height)
                                logFlick.contentY = Math.max(
                                    0, logFlick.contentHeight - logFlick.height)
                        })
                    }
                }
            }
        }

        Row {
            id: btnRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            anchors.bottomMargin: 12
            height: 30
            spacing: 8
            ThemedButton {
                id: btnStart
                label: app.captureRunning ? "Arrêter la capture" : "Démarrer la capture"
                accent: !app.captureRunning
                onClicked: {
                    if (app.captureRunning)
                        app.stopCapture()
                    else
                        app.startCapture()
                }
            }
            ThemedButton {
                label: app.overlayEnabled ? "Fermer overlay" : "Overlay"
                tooltip: "Petit panneau toujours visible : coût, temps, tentatives d'exo"
                accent: app.overlayEnabled
                onClicked: app.setOverlayEnabled(!app.overlayEnabled)
            }
            ThemedButton {
                label: "Reset"
                tooltip: "Remet à zéro poses, exo, succès et historique de cet item"
                onClicked: app.resetItemSession()
            }
            ThemedButton {
                label: "Rejouer"
                tooltip: "Ouvrir un journal frames.jsonl"
                onClicked: replayDialog.open()
            }
        }
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: app.tick()
    }
}
