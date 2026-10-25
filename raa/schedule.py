"""RAA scheduling core: doubly linked list + hash map (spec data structures).

- DoublyLinkedList: chronological (deadline, order_index) event ordering
  with O(1) splice in/out. Node prev/next pointers are plain references.
- Hash map lookup: Schedule.nodes dict maps event_id -> Node (O(1)).
- Insert/reschedule/cancel are local splice operations; the whole list is
  NEVER rebuilt for a positional change. Durations ("available time") are
  derived from each event's deadline and the schedule start time
  (deadline - schedule_start for the first event; deadline - predecessor's
  deadline afterwards), so no synthetic task-duration CSV is used.
"""
import time


class Node:
    __slots__ = ("event_id", "component_id", "category", "deadline_unix_sec",
                 "duration_s", "order_index", "prev", "next")

    def __init__(self, event_id, component_id, category, deadline_unix_sec,
                 duration_s=0, order_index=0):
        self.event_id = event_id
        self.component_id = component_id
        self.category = category
        self.deadline_unix_sec = int(deadline_unix_sec)
        self.duration_s = int(duration_s)
        self.order_index = int(order_index)
        self.prev = None
        self.next = None

    def as_dict(self):
        return {"event_id": self.event_id,
                "component_id": self.component_id,
                "category": self.category,
                "deadline_unix_sec": self.deadline_unix_sec,
                "duration_s": self.duration_s,
                "order_index": self.order_index}


class DoublyLinkedList:
    def __init__(self):
        self.head = None
        self.tail = None
        self.count = 0

    def insert_node(self, node):
        """Insert preserving (deadline, order_index) order. O(n) scan, O(1)
        splice — NO rebuild of existing nodes."""
        if self.head is None:
            self.head = self.tail = node
        else:
            cur = self.head
            while cur is not None and (cur.deadline_unix_sec,
                                       cur.order_index) <= (
                    node.deadline_unix_sec, node.order_index):
                cur = cur.next
            if cur is None:                      # append at tail
                node.prev = self.tail
                node.prev.next = node
                self.tail = node
            else:                                # splice before cur
                node.prev = cur.prev
                node.next = cur
                cur.prev = node
                if node.prev is None:
                    self.head = node
                else:
                    node.prev.next = node
        self.count += 1
        return node

    def remove_node(self, node):
        """O(1) unlink; neighbouring node objects are untouched."""
        if node.prev is None:
            self.head = node.next
        else:
            node.prev.next = node.next
        if node.next is None:
            self.tail = node.prev
        else:
            node.next.prev = node.prev
        node.prev = node.next = None
        self.count -= 1
        return node

    def iter_from(self, node=None):
        cur = node if node is not None else self.head
        while cur is not None:
            yield cur
            cur = cur.next


class Schedule:
    """Doubly linked list + hash map. Retries are safe: inserting an
    existing event_id updates that node in place (upsert)."""

    def __init__(self):
        self.dll = DoublyLinkedList()
        self.nodes = {}        # hash map: event_id -> Node

    # -- lookups ------------------------------------------------------------
    def find(self, event_id):
        return self.nodes.get(event_id)

    def __len__(self):
        return self.dll.count

    def order(self):
        return [n.as_dict() for n in self.dll.iter_from()]

    def neighbours_of(self, event_id):
        n = self.nodes.get(event_id)
        if n is None:
            return (None, None)
        return (n.prev.event_id if n.prev else None,
                n.next.event_id if n.next else None)

    # -- operations -----------------------------------------------------------
    def upsert(self, component_id, category, deadline_unix_sec,
               schedule_start=None, order_index=0):
        """Insert or move an event chronologically. duration_s is derived
        from the deadline and the relevant schedule/start time, never from
        invented task data."""
        deadline = int(deadline_unix_sec)
        event_id = self._event_id(component_id, category)
        existing = self.nodes.get(event_id)
        if existing is not None:
            self.dll.remove_node(existing)      # relocations keep the id
        node = Node(event_id, component_id, category, deadline,
                    duration_s=0, order_index=order_index)
        # structural splice only; neighbouring node objects are untouched
        self.dll.insert_node(node)
        self.nodes[event_id] = node
        self._recompute_durations(schedule_start)
        return node

    def cancel(self, component_id, category):
        event_id = self._event_id(component_id, category)
        node = self.nodes.pop(event_id, None)
        if node is None:
            return None
        self.dll.remove_node(node)
        self._recompute_durations()
        return node

    def _recompute_durations(self, schedule_start=None):
        """After any positional change, available time for each event is
        deadline - (predecessor's deadline or schedule start)."""
        prev_deadline = schedule_start
        for node in self.dll.iter_from():
            if prev_deadline is None:
                node.duration_s = 0
            else:
                node.duration_s = max(0, node.deadline_unix_sec -
                                      int(prev_deadline))
            prev_deadline = node.deadline_unix_sec

    def restore(self, event_dicts):
        """Rebuild from persisted rows (R2 recovery). Existing node objects
        are replaced; the list is rebuilt only on restore."""
        self.dll = DoublyLinkedList()
        self.nodes = {}
        rows = sorted(event_dicts,
                      key=lambda e: (e["deadline_unix_sec"],
                                     e.get("order_index", 0)))
        for e in rows:
            node = Node(e["event_id"], e["component_id"], e["category"],
                        e["deadline_unix_sec"], e.get("duration_s", 0),
                        e.get("order_index", 0))
            self.dll.insert_node(node)
            self.nodes[node.event_id] = node
        return len(rows)

    @staticmethod
    def _event_id(component_id, category):
        if not component_id:
            raise ValueError("event requires component_id")
        return "%s@%s" % (component_id, category or "")

    def free_slots(self, min_len_s=0):
        """Gaps between consecutive deadlines (>= min_len_s)."""
        slots = []
        prev = None
        for n in self.dll.iter_from():
            if prev is not None:
                gap = n.deadline_unix_sec - prev.deadline_unix_sec
                if gap >= min_len_s:
                    slots.append({"start_unix_sec": prev.deadline_unix_sec,
                                  "end_unix_sec": n.deadline_unix_sec,
                                  "gap_s": gap})
            prev = n
        return slots
