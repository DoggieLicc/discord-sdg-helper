from __future__ import annotations

import copy
import random

from dataclasses import dataclass

import utils
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
class Modifier:
    def modify_valid_roles(self, in_roles: list[Role], prev_roles: list[Role]) -> list[Role]:
        ...


@dataclass
class MutualExclusiveModifier(Modifier):
    mutual_exclusive_roles: list[Role]

    def modify_valid_roles(self, in_roles: list[Role], prev_roles: list[Role]) -> list[Role]:
        valid_roles = []
        for role in in_roles:
            if role not in self.mutual_exclusive_roles:
                valid_roles.append(role)
                continue

            is_valid = True
            for prev_role in prev_roles:
                if prev_role in self.mutual_exclusive_roles:
                    is_valid = False

            if not is_valid:
                continue

            valid_roles.append(role)

        return valid_roles


@dataclass
class LimitModifier(Modifier):
    limited_roles: list[Role]
    limit: int

    def modify_valid_roles(self, in_roles: list[Role], prev_roles: list[Role]) -> list[Role]:
        valid_roles = []
        num_roles = 0

        for prev_role in prev_roles:
            if prev_role in self.limited_roles:
                num_roles += 1

        for in_role in in_roles:
            if in_role not in self.limited_roles or num_roles < self.limit:
                valid_roles.append(in_role)

        return valid_roles


@dataclass
class IndividualityModifier(Modifier):
    indv_roles: list[Role]

    def modify_valid_roles(self, in_roles: list[Role], prev_roles: list[Role]) -> list[Role]:
        valid_roles = []
        for role in in_roles:
            if role not in self.indv_roles or role not in prev_roles:
                valid_roles.append(role)

        return valid_roles


@dataclass
class WeightChanger:
    roles: list[Role]
    argument: int

    def get_weight(self, prev_weight: int) -> int:
        ...

    def check_role(self, role) -> bool:
        return role in self.roles



@dataclass
class WeightSet(WeightChanger):
    def get_weight(self, prev_weight: int) -> int:
        return self.argument


@dataclass
class WeightAdder(WeightChanger):
    def get_weight(self, prev_weight: int) -> int:
        return prev_weight + self.argument


@dataclass
class WeightSubtractor(WeightChanger):
    def get_weight(self, prev_weight: int) -> int:
        return prev_weight - self.argument


@dataclass
class WeightDivider(WeightChanger):
    def get_weight(self, prev_weight: int) -> int | float:
        return prev_weight / self.argument


@dataclass
class WeightMultiplier(WeightChanger):
    def get_weight(self, prev_weight: int):
        return prev_weight * self.argument


@dataclass
class Slot:
    filters: list[Filter]
    ignore_global: bool


@dataclass
class Rolelist:
    slots: list[Slot]
    global_filters: list[Filter]
    modifiers: list[Modifier]
    weight_changers: list[WeightChanger]


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


def process_filters(in_roles: list[Role], filters: list[Filter]) -> list[Role]:
    for filter in filters:
        in_roles = filter.filter_roles(in_roles)

    return in_roles


def get_str_modifier(modifier_str: str, all_roles: list[Role]) -> Modifier:
    arguments = modifier_str.split(':')
    modifier_name = arguments[0].lower().strip()

    if modifier_name in ['individual', 'individuality', 'indv']:
        roles_str = arguments[1].strip() if len(arguments) >= 2 else ''
        filters = get_str_filters(roles_str).filters
        if roles_str:
            roles = process_filters(all_roles, filters)
        else:
            roles = all_roles

        if not roles:
            raise utils.SDGException(f'No roles for {roles_str}')

        return IndividualityModifier(roles)

    if modifier_name in ['limit', 'lim', 'rolelimit']:
        roles_str = arguments[1].strip()
        limit = int(arguments[2].strip()) if len(arguments) >= 3 else 1
        filters = get_str_filters(roles_str).filters
        roles = process_filters(all_roles, filters)

        if not roles:
            raise utils.SDGException(f'No roles for {roles_str}')

        return LimitModifier(roles, limit)

    if modifier_name in ['exclusive', 'mutualexclusive', 'mutualexclusivity', 'mutexclusive', 'mexc']:
        roles_str = arguments[1].strip()
        filters = get_str_filters(roles_str).filters
        roles = process_filters(all_roles, filters)

        if not roles:
            raise utils.SDGException(f'No roles for {roles_str}')

        return MutualExclusiveModifier(roles)

    raise Exception('Invalid modifier')


def get_weight_chnager(in_str, all_roles: list[Role]) -> WeightChanger:
    arguments = in_str.split(':')
    parameter = arguments[1].lower().strip()
    symbol = parameter[0]
    number = int(parameter[1:])
    
    roles_str = arguments[0].lower().strip()
    filters = get_str_filters(roles_str).filters
    roles = process_filters(all_roles, filters)

    if not roles:
        raise utils.SDGException(f'No roles for {roles_str} in ={in_str}')
    
    if symbol.isnumeric():
        return WeightSet(roles, int(parameter))
    
    if symbol == '+':
        return WeightAdder(roles, number)
    
    if symbol == '-':
        return WeightSubtractor(roles, number)
    
    if symbol in ['*', 'x']:
        return WeightMultiplier(roles, number)
    
    if symbol == '/':
        return WeightDivider(roles, number)


def get_role_weight(role: Role, weight_changers: list[WeightChanger]) -> int:
    valid_weights_changers = [w for w in weight_changers if w.check_role(role)]
    weight = 10

    for changer in valid_weights_changers:
        weight = changer.get_weight(weight)

    if weight <= 0:
        raise utils.SDGException(f'Weight of {role.name} was resolved to {weight}, under or equal to 0')

    return weight


def get_all_weights(roles: list[Role], weight_changers: list[WeightChanger]) -> list[int]:
    weights = []

    for role in roles:
        weights.append(get_role_weight(role, weight_changers))

    return weights


def get_rolelist(message_str: str, all_roles: list[Role]) -> Rolelist:
    message_lines = message_str.splitlines()
    global_filters = []
    slots = []
    modifiers = []
    weights = []
    for line in message_lines:
        if not line:
            continue
        if line.startswith('+'):
            slot_str = line[1:]
            fake_slot = get_str_filters(slot_str)
            global_filters += fake_slot.filters
            continue
        if line.startswith('?'):
            modifier_str = line[1:]
            modifiers.append(get_str_modifier(modifier_str, all_roles))
            continue
        if line.startswith('='):
            weight_str = line[1:]
            weights.append(get_weight_chnager(weight_str, all_roles))
            continue

        slot = get_str_filters(line)
        slots.append(slot)

    return Rolelist(slots=slots, global_filters=global_filters, modifiers=modifiers, weight_changers=weights)


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

        for modifier in rolelist.modifiers:
            valid_roles = modifier.modify_valid_roles(valid_roles, roles)

        if not valid_roles:
            raise utils.SDGException(f'No valid roles for {slot}')

        if not rolelist.weight_changers:
            roles.append(random.choice(valid_roles))
        else:
            weights = get_all_weights(valid_roles, rolelist.weight_changers)
            role = random.choices(valid_roles, weights=weights, k=1)[0]
            roles.append(role)

    return roles

