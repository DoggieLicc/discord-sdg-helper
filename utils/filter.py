import copy
import random

from dataclasses import dataclass
from utils import Role


@dataclass
class Filter:
    negated: bool
    filter_str: str

    def filter_roles(self, in_roles: list[Role]) -> list[Role]:
        ...


@dataclass
class RoleFilter(Filter):
    def filter_roles(self, in_roles: list[Role]) -> list[Role]:
        valid_roles = []
        for role in in_roles:
            add_role = role.name.lower().strip() == self.filter_str.lower().strip()
            if self.negated:
                add_role = not add_role

            if add_role:
                valid_roles.append(role)

        return valid_roles


@dataclass
class FactionFilter(Filter):
    def filter_roles(self, in_roles: list[Role]) -> list[Role]:
        valid_roles = []
        for role in in_roles:
            add_role = role.faction.name.lower().strip() == self.filter_str.lower().strip()
            if self.negated:
                add_role = not add_role

            if add_role:
                valid_roles.append(role)

        return valid_roles


@dataclass
class TagFilter(Filter):
    def filter_roles(self, in_roles) -> list[Role]:
        if self.filter_str == 'ANY':
            return in_roles if not self.negated else None

        valid_roles = []
        for role in in_roles:
            add_role = False
            forum_tags = list(role.forum_tags) + [role.subalignment.name]
            for tag in forum_tags:
                if tag.lower().strip() == self.filter_str.lower().strip():
                    add_role = True
                    continue

            if self.negated:
                add_role = not add_role

            if add_role:
                valid_roles.append(role)

        return valid_roles


@dataclass
class UnionFilter(Filter):
    unioned_filters: list[Filter]

    def filter_roles(self, in_roles) -> list[Role]:
        valid_roles = []

        for _filter in self.unioned_filters:
            for role in _filter.filter_roles(in_roles):
                if role not in valid_roles:
                    valid_roles.append(role)

        return valid_roles


@dataclass
class Slot:
    filters: list[Filter]
    ignore_global: bool


@dataclass
class Rolelist:
    slots: list[Slot]
    global_filters: list[Filter]


filter_dict = {
    '%': RoleFilter,
    '$': FactionFilter,
    '&': None,
    '|': None,
    '!': None
}


def get_str_filters(slot_str: str) -> Slot:
    filter_chars = ''
    next_filter = None
    negate_next_filter = False
    ignore_global = False
    filters = []
    unioned_filters = []
    union_next_filter = False

    if slot_str.startswith('-'):
        ignore_global = True
        slot_str = slot_str[1:]

    for char in slot_str:

        if char == r'\'':
            continue

        if char in filter_dict.keys():
            if filter_chars and not next_filter:
                next_filter = TagFilter

            if next_filter:
                new_filter = next_filter(
                        negated=negate_next_filter,
                        filter_str=filter_chars
                    )
                filter_chars = ''
                negate_next_filter = False

                if union_next_filter:
                    unioned_filters.append(new_filter)
                    union_next_filter = False
                else:
                    filters.append(new_filter)

            if char == '|':
                if not unioned_filters:
                    prev_filter = filters.pop(len(filters)-1)
                    unioned_filters.append(prev_filter)

                union_next_filter = True

            if unioned_filters and not union_next_filter:
                union_filter = UnionFilter(
                    filter_str='',
                    negated=False,
                    unioned_filters=unioned_filters
                )
                filters.append(union_filter)

            next_filter = filter_dict[char]

            if char == '!':
                negate_next_filter = True

            continue

        filter_chars += char

    if filter_chars and not next_filter:
        next_filter = TagFilter

    if next_filter:
        new_filter = next_filter(negated=negate_next_filter, filter_str=filter_chars)

        if union_next_filter:
            unioned_filters.append(new_filter)
        else:
            filters.append(new_filter)

    if unioned_filters:
        union_filter = UnionFilter(
            filter_str='',
            negated=False,
            unioned_filters=unioned_filters
        )
        filters.append(union_filter)

    return Slot(filters=filters, ignore_global=ignore_global)


def get_rolelist(message_str: str) -> Rolelist:
    message_lines = message_str.splitlines()
    global_filters = []
    slots = []
    for line in message_lines:
        if not line:
            continue
        if line.startswith('+'):
            slot_str = line[1:]
            fake_slot = get_str_filters(slot_str)
            global_filters += fake_slot.filters
            continue

        slot = get_str_filters(line)
        slots.append(slot)

    return Rolelist(slots=slots, global_filters=global_filters)


def generate_rolelist_roles(rolelist: Rolelist, input_roles: list[Role]) -> list[Role]:
    new_slots = []
    roles = []

    for slot in rolelist.slots:
        if not slot.ignore_global:
            slot.filters += rolelist.global_filters

        new_slots.append(slot)

    for slot in new_slots:
        valid_roles = copy.deepcopy(input_roles)
        for r_filter in slot.filters:
            valid_roles = r_filter.filter_roles(valid_roles)

        if not valid_roles:
            raise Exception(f'No valid roles for {slot}')

        roles.append(random.choice(valid_roles))

    return roles

