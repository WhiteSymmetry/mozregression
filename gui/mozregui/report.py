from PySide.QtGui import QTextBrowser, QTableView, QDesktopServices
from PySide.QtCore import QAbstractTableModel, QModelIndex, Qt, Slot, Signal, \
    QUrl


class ReportItem(object):
    """
    A base item in the report view
    """
    def __init__(self):
        self.data = {}

    def update_pushlogurl(self, bisection):
        self.data['pushlog_url'] = bisection.handler.get_pushlog_url()

    def status_text(self):
        return "Looking for build data..."


class StartItem(ReportItem):
    """
    Report a started bisection
    """
    def update_pushlogurl(self, bisection):
        ReportItem.update_pushlogurl(self, bisection)
        handler = bisection.handler
        self.build_type = handler.build_type
        if handler.build_type == 'nightly':
            self.first, self.last = handler.get_date_range()
        else:
            self.first, self.last = handler.get_range()

    def status_text(self):
        if 'pushlog_url' not in self.data:
            return ReportItem.status_text(self)
        return 'Started %s [%s - %s]' % (self.build_type,
                                         self.first, self.last)


class StepItem(ReportItem):
    """
    Report a bisection step
    """
    def __init__(self):
        ReportItem.__init__(self)
        self.verdict = None

    def status_text(self):
        if not self.data:
            return ReportItem.status_text(self)
        if self.data['build_type'] == 'nightly':
            msg = "Found nightly build: %s" % self.data['build_date']
        else:
            msg = "Found inbound build: %s" % self.data['changeset']
        if self.verdict is not None:
            msg += ' (verdict: %s)' % self.verdict
        return msg


class ReportModel(QAbstractTableModel):
    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.items = []

    def clear(self):
        self.beginResetModel()
        self.items = []
        self.endResetModel()

    @Slot(object)
    def attach_bisector(self, bisector):
        bisector.step_started.connect(self.step_started)
        bisector.step_build_found.connect(self.step_build_found)
        bisector.step_finished.connect(self.step_finished)
        bisector.started.connect(self.started)
        bisector.finished.connect(self.finished)

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            item = self.items[index.row()]
            return item.status_text()
        return None

    def update_item(self, item):
        index = self.createIndex(self.items.index(item), 0)
        self.dataChanged.emit(index, index)

    def append_item(self, item):
        row = self.rowCount()
        self.beginInsertRows(QModelIndex(), row, row)
        self.items.append(item)
        self.endInsertRows()

    @Slot()
    def started(self):
        # when a bisection starts, insert an item to report it
        self.append_item(StartItem())

    @Slot(object, int)
    def step_started(self, bisection):
        last_item = self.items[-1]
        if isinstance(last_item, StepItem):
            # update the pushlog for the last step
            last_item.update_pushlogurl(bisection)
            self.update_item(last_item)
            # and add a new step
            self.append_item(StepItem())

    @Slot(object, int, object)
    def step_build_found(self, bisection, build_infos):
        last_item = self.items[-1]

        if isinstance(last_item, StartItem):
            # update the pushlog for the start step
            last_item.update_pushlogurl(bisection)
            self.update_item(last_item)

            # and add the new step with build_infos
            item = StepItem()
            item.data.update(build_infos)
            self.append_item(item)
        else:
            # previous item is a step, just update it
            last_item.data.update(build_infos)
            self.update_item(last_item)

    @Slot(object, int, str)
    def step_finished(self, bisection, verdict):
        # step finished, just store the verdict
        item = self.items[-1]
        item.verdict = verdict
        self.update_item(item)

    @Slot(object, int)
    def finished(self, bisection, result):
        # remove the last insterted step
        index = len(self.items) - 1
        self.beginRemoveRows(QModelIndex(), index, index)
        self.items.pop(index)
        self.endRemoveRows()


class ReportView(QTableView):
    step_report_selected = Signal(object)

    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self._model = ReportModel()
        self.setModel(self._model)

    def currentChanged(self, current, previous):
        item = self._model.items[current.row()]
        self.step_report_selected.emit(item)


class BuildInfoTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        QTextBrowser.__init__(self, parent)
        self.anchorClicked.connect(self.on_anchor_clicked)

    @Slot(object)
    def update_content(self, item):
        if not item.data:
            self.clear()
            return

        html = ""
        for k in sorted(item.data):
            v = item.data[k]
            html += '<strong>%s</strong>: ' % k
            if isinstance(v, basestring):
                url = QUrl(v)
                if url.isValid() and url.scheme():
                    v = '<a href="%s">%s</a>' % (v, v)
            html += '%s<br>' % v
        self.setHtml(html)

    @Slot(QUrl)
    def on_anchor_clicked(self, url):
        QDesktopServices.openUrl(url)
