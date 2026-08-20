import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property string title: ""
    property bool clipContent: true
    default property alias content: body.data

    radius: Colors.radius_card
    color: Colors.bg_card
    border.width: 1
    border.color: Colors.separator

    Text {
        id: titleLabel
        visible: root.title.length > 0
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 10
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        text: root.title
        color: Colors.text_muted
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_secondary
        font.bold: true
        textFormat: Text.PlainText
    }

    Item {
        id: body
        anchors.top: titleLabel.visible ? titleLabel.bottom : parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.topMargin: titleLabel.visible ? 8 : 12
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.bottomMargin: 12
        clip: root.clipContent
    }
}
