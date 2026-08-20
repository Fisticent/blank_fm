import QtQuick
import QtQuick.Window

Window {
    id: overlay
    title: "Dofus FM overlay"
    width: app.overlayW >= 180 ? app.overlayW : 268
    height: app.overlayH >= 120 ? app.overlayH : 210
    minimumWidth: 180
    minimumHeight: 120
    visible: app.overlayEnabled
    color: "#00000000"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    transientParent: null
    x: app.overlayX >= 0 ? app.overlayX : 48
    y: app.overlayY >= 0 ? app.overlayY : 96

    readonly property int grip: 14

    function persist() {
        app.saveOverlayGeometry(overlay.x, overlay.y, overlay.width, overlay.height)
    }

    onVisibleChanged: {
        if (visible) {
            overlay.raise()
            overlay.requestActivate()
        }
    }

    Rectangle {
        id: card
        anchors.fill: parent
        radius: Colors.radius_card
        color: Colors.bg_card
        border.width: 1
        border.color: Colors.separator
        opacity: 0.94
        clip: true

        MouseArea {
            anchors.fill: parent
            anchors.rightMargin: overlay.grip
            anchors.bottomMargin: overlay.grip
            property point start
            onPressed: (mouse) => start = Qt.point(mouse.x, mouse.y)
            onPositionChanged: (mouse) => {
                if (mouse.buttons & Qt.LeftButton) {
                    overlay.x += mouse.x - start.x
                    overlay.y += mouse.y - start.y
                }
            }
            onReleased: overlay.persist()
        }

        Column {
            id: body
            anchors.fill: parent
            anchors.margins: 10
            anchors.bottomMargin: 18
            spacing: 6

            Row {
                width: parent.width
                spacing: 8

                Rectangle {
                    width: 32
                    height: 32
                    radius: Colors.radius_control
                    color: Colors.bg
                    border.width: 1
                    border.color: Colors.separator
                    Image {
                        id: overlayItemIcon
                        anchors.fill: parent
                        anchors.margins: 2
                        source: app.itemIcon
                        fillMode: Image.PreserveAspectFit
                    }
                    Text {
                        visible: overlayItemIcon.status !== Image.Ready
                        anchors.centerIn: parent
                        text: app.itemGid > 0 ? app.itemName.charAt(0).toUpperCase() : "?"
                        color: Colors.text_muted
                        font.family: Colors.font_family
                        font.pixelSize: 14
                        font.bold: true
                    }
                }

                Text {
                    text: app.itemGid > 0 ? app.itemName : "Dofus FM"
                    color: Colors.text
                    font.family: Colors.font_family
                    font.pixelSize: Colors.font_size_ui
                    font.bold: true
                    elide: Text.ElideRight
                    width: Math.max(40, parent.width - 32 - 8 - rightBtns.width - 8)
                    anchors.verticalCenter: parent.verticalCenter
                }

                Row {
                    id: rightBtns
                    spacing: 4
                    anchors.verticalCenter: parent.verticalCenter

                    Rectangle {
                        id: btnReset
                        width: 22
                        height: 22
                        radius: 4
                        color: resetMouse.containsMouse ? Colors.secondary_hover : "#00000000"

                        Canvas {
                            id: resetIcon
                            anchors.fill: parent
                            anchors.margins: 3
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                var w = width
                                var h = height
                                var cx = w / 2
                                var cy = h / 2
                                var r = Math.min(w, h) / 2 - 0.5
                                ctx.strokeStyle = resetMouse.containsMouse ? Colors.warning : Colors.text_muted
                                ctx.fillStyle = ctx.strokeStyle
                                ctx.lineWidth = 1.7
                                ctx.lineCap = "round"
                                ctx.beginPath()
                                ctx.arc(cx, cy, r, 0.45 * Math.PI, 1.95 * Math.PI, false)
                                ctx.stroke()
                                var ang = 0.45 * Math.PI
                                var ax = cx + r * Math.cos(ang)
                                var ay = cy + r * Math.sin(ang)
                                ctx.beginPath()
                                ctx.moveTo(ax + 3.2, ay - 0.4)
                                ctx.lineTo(ax - 2.4, ay + 3.4)
                                ctx.lineTo(ax - 3.6, ay - 2.8)
                                ctx.closePath()
                                ctx.fill()
                            }
                        }

                        MouseArea {
                            id: resetMouse
                            anchors.fill: parent
                            anchors.margins: -3
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: app.resetItemSession()
                            onContainsMouseChanged: resetIcon.requestPaint()
                        }

                        Rectangle {
                            visible: resetMouse.containsMouse
                            z: 20
                            width: resetTip.width + 12
                            height: resetTip.height + 8
                            radius: 4
                            color: Colors.tooltip_bg
                            anchors.top: parent.bottom
                            anchors.topMargin: 4
                            anchors.horizontalCenter: parent.horizontalCenter
                            Text {
                                id: resetTip
                                anchors.centerIn: parent
                                text: "Reset"
                                color: Colors.tooltip_fg
                                font.family: Colors.font_family
                                font.pixelSize: Colors.font_size_secondary
                            }
                        }
                    }

                    Text {
                        text: "✕"
                        color: closeMouse.containsMouse ? Colors.text : Colors.text_muted
                        font.family: Colors.font_family
                        font.pixelSize: Colors.font_size_ui
                        width: 16
                        height: 22
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        MouseArea {
                            id: closeMouse
                            anchors.fill: parent
                            anchors.margins: -4
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: app.setOverlayEnabled(false)
                        }
                    }
                }
            }

            KamaAmount {
                amount: app.costFormatted
                iconSize: 16
                pixelSize: 18
                bold: true
                width: parent.width
            }
            Text {
                text: app.poses + " pose(s)"
                color: Colors.text_muted
                font.family: Colors.font_family
                font.pixelSize: Colors.font_size_secondary
            }
            Text {
                text: "Session  " + app.sessionDuration + (app.timerPaused ? "  pause" : "")
                color: app.timerPaused ? Colors.text_muted : Colors.primary_bright
                font.family: Colors.font_family
                font.pixelSize: Colors.font_size_ui
                font.bold: true
            }
            Text {
                text: "Item  " + app.itemDuration
                color: Colors.text_muted
                font.family: Colors.font_family
                font.pixelSize: Colors.font_size_secondary
            }

            Row {
                visible: app.exoLastCostFormatted.length > 0 || app.exoAvgCostFormatted.length > 0
                width: parent.width
                spacing: 8
                Text {
                    text: "Tenta"
                    color: Colors.text_muted
                    font.family: Colors.font_family
                    font.pixelSize: Colors.font_size_secondary
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                KamaAmount {
                    amount: app.exoLastCostFormatted
                    iconSize: 12
                    pixelSize: Colors.font_size_ui
                    bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    visible: app.exoAvgCostFormatted.length > 0
                    text: "moy"
                    color: Colors.text_muted
                    font.family: Colors.font_family
                    font.pixelSize: Colors.font_size_secondary
                    anchors.verticalCenter: parent.verticalCenter
                }
                KamaAmount {
                    amount: app.exoAvgCostFormatted
                    suffix: "/t"
                    iconSize: 12
                    pixelSize: Colors.font_size_secondary
                    textColor: Colors.text_muted
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Text {
                visible: app.exoAttemptsActiveModel.length > 0
                text: "TENTATIVES D'EXO"
                color: Colors.text_muted
                font.family: Colors.font_family
                font.pixelSize: 10
                font.bold: true
            }
            Flow {
                visible: app.exoAttemptsActiveModel.length > 0
                width: parent.width
                spacing: 8
                Repeater {
                    model: app.exoAttemptsActiveModel
                    Row {
                        spacing: 4
                        Text {
                            text: modelData.label
                            color: Colors.text_muted
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                        Text {
                            text: "" + modelData.attempts
                            color: modelData.color
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_ui
                            font.bold: true
                        }
                        Text {
                            visible: modelData.landed > 0
                            text: "(" + modelData.landed + ")"
                            color: Colors.success
                            font.family: Colors.font_family
                            font.pixelSize: Colors.font_size_secondary
                            font.bold: true
                        }
                    }
                }
            }
        }

        Item {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: overlay.grip
            height: overlay.grip
            MouseArea {
                id: resizeGrip
                anchors.fill: parent
                cursorShape: Qt.SizeFDiagCursor
                property real startW
                property real startH
                property point start
                onPressed: (mouse) => {
                    start = resizeGrip.mapToGlobal(mouse.x, mouse.y)
                    startW = overlay.width
                    startH = overlay.height
                }
                onPositionChanged: (mouse) => {
                    if (mouse.buttons & Qt.LeftButton) {
                        var g = resizeGrip.mapToGlobal(mouse.x, mouse.y)
                        overlay.width = Math.max(overlay.minimumWidth, startW + g.x - start.x)
                        overlay.height = Math.max(overlay.minimumHeight, startH + g.y - start.y)
                    }
                }
                onReleased: overlay.persist()
            }
            Canvas {
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = Colors.separator
                    ctx.lineWidth = 1.5
                    for (var i = 1; i <= 3; i++) {
                        ctx.beginPath()
                        ctx.moveTo(width - 2, height - 3 * i)
                        ctx.lineTo(width - 3 * i, height - 2)
                        ctx.stroke()
                    }
                }
            }
        }
    }
}
