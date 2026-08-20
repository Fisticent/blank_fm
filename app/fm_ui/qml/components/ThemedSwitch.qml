import QtQuick
import QtQuick.Controls

Item {
    id: root
    property bool checked: false
    signal clicked()

    implicitWidth: 44
    implicitHeight: 22
    width: implicitWidth
    height: implicitHeight

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.checked ? Colors.primary : Colors.secondary
        border.width: 1
        border.color: root.checked ? Colors.primary_bright : Colors.separator

        Rectangle {
            width: 16
            height: 16
            radius: 8
            color: Colors.text
            anchors.verticalCenter: parent.verticalCenter
            x: root.checked ? parent.width - width - 3 : 3
            Behavior on x { NumberAnimation { duration: 90 } }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
