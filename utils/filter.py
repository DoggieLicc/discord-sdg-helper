from __future__ import annotations

import random

from dataclasses import dataclass
from abc import ABC, abstractmethod

from utils.classes import Role, SDGException


__all__ = [
    'generate_rolelist_roles',
    'get_rolelist'
]


@dataclass(frozen=True)
class PartialRole:
    id: int
    name: str
    faction_name: str
    tags: frozenset[str]

    @classmethod
    def from_role(cls, role: Role) -> PartialRole:
        tags = role.forum_tags | {role.subalignment.name}
        partial_role = cls(
            id=role.id,
            name=role.name,
            faction_name=role.faction.name,
            tags=frozenset(tags),
        )
        return partial_role

    def to_role(self, full_roles: list[Role]) -> Role:
        for role in full_roles:
            if role.id == self.id:
                return role
        raise SDGException(f'Unable to convert partial role {self.name} to full role')


@dataclass(slots=True)
class Filter(ABC):
    negated: bool
    filter_str: str

    @abstractmethod
    def filter_roles(self, in_roles: set[PartialRole]) -> set[PartialRole]:
        ...


@dataclass(slots=True)
class RoleFilter(Filter):
    def filter_roles(self, in_roles: set[PartialRole]) -> set[PartialRole]:
        valid_roles = set()
        for role in in_roles:
            add_role = role.name.lower().strip() == self.filter_str.lower().strip()
            if self.negated:
                add_role = not add_role

            if add_role:
                valid_roles.add(role)

        return valid_roles


@dataclass(slots=True)
class FactionFilter(Filter):
    def filter_roles(self, in_roles: set[PartialRole]) -> set[PartialRole]:
        valid_roles = set()
        filter_name = self.filter_str.lower().strip()
        for role in in_roles:
            add_role = role.faction_name.lower().strip() == filter_name
            if self.negated:
                add_role = not add_role

            if add_role:
                valid_roles.add(role)

        return valid_roles


@dataclass(slots=True)
class TagFilter(Filter):
    def filter_roles(self, in_roles: set[PartialRole]) -> set[PartialRole]:
        if self.filter_str == 'ANY':
            return in_roles if not self.negated else set()

        valid_roles = set()
        for role in in_roles:
            add_role = False
            for tag in role.tags:
                if tag.lower().strip() == self.filter_str.lower().strip():
                    add_role = True
                    continue

            if self.negated:
                add_role = not add_role

            if add_role:
                valid_roles.add(role)

        return valid_roles


@dataclass(slots=True)
class UnionFilter(Filter):
    unioned_filters: list[Filter]

    def filter_roles(self, in_roles: set[PartialRole]) -> set[PartialRole]:
        valid_roles = set()

        for _filter in self.unioned_filters:
            for role in _filter.filter_roles(in_roles):
                if role not in valid_roles:
                    valid_roles.add(role)

        return valid_roles


@dataclass(slots=True)
class Modifier(ABC):
    @abstractmethod
    def modify_valid_roles(self, in_roles: set[PartialRole], prev_roles: list[PartialRole]) -> set[PartialRole]:
        ...


@dataclass(slots=True)
class MutualExclusiveModifier(Modifier):
    mutual_exclusive_roles: set[PartialRole]
    mutual_exclusive_roles2: None | set[PartialRole] = None

    def modify_valid_roles(self, in_roles: set[PartialRole], prev_roles: list[PartialRole]) -> set[PartialRole]:
        valid_roles = set()
        if self.mutual_exclusive_roles2 is None:
            for role in in_roles:
                if role not in self.mutual_exclusive_roles:
                    valid_roles.add(role)
                    continue

                is_valid = True
                for prev_role in prev_roles:
                    if prev_role in self.mutual_exclusive_roles:
                        is_valid = False
                        break

                if is_valid:
                    valid_roles.add(role)
        else:
            all_mut_roles = self.mutual_exclusive_roles | self.mutual_exclusive_roles2
            for role in in_roles:
                if role not in all_mut_roles:
                    valid_roles.add(role)
                    continue

                is_valid = True
                for prev_role in prev_roles:
                    if role in self.mutual_exclusive_roles:
                        if prev_role in self.mutual_exclusive_roles2:
                            is_valid = False
                            break

                    if role in self.mutual_exclusive_roles2:
                        if prev_role in self.mutual_exclusive_roles:
                            is_valid = False
                            break

                if is_valid:
                    valid_roles.add(role)

        return valid_roles


@dataclass(slots=True)
class LimitModifier(Modifier):
    limited_roles: set[PartialRole]
    limit: int

    def modify_valid_roles(self, in_roles: set[PartialRole], prev_roles: list[PartialRole]) -> set[PartialRole]:
        valid_roles = set()
        num_roles = 0

        for prev_role in prev_roles:
            if prev_role in self.limited_roles:
                num_roles += 1

        for in_role in in_roles:
            if in_role not in self.limited_roles or num_roles < self.limit:
                valid_roles.add(in_role)

        return valid_roles


@dataclass(slots=True)
class IndividualityModifier(Modifier):
    indv_roles: set[PartialRole]

    def modify_valid_roles(self, in_roles: set[PartialRole], prev_roles: list[PartialRole]) -> set[PartialRole]:
        valid_roles = set()
        for role in in_roles:
            if role not in self.indv_roles or role not in prev_roles:
                valid_roles.add(role)

        return valid_roles


@dataclass(slots=True)
class WeightChanger(ABC):
    roles: set[PartialRole]
    argument: int
    limit: int | None

    @abstractmethod
    def get_weight(self, prev_weight: int) -> int:
        ...

    def check_role(self, role) -> bool:
        return role in self.roles


@dataclass(slots=True)
class WeightSet(WeightChanger):
    def get_weight(self, prev_weight: int) -> int:
        return self.argument


@dataclass(slots=True)
class WeightAdder(WeightChanger):
    def get_weight(self, prev_weight: int) -> int:
        return prev_weight + self.argument


@dataclass(slots=True)
class WeightSubtractor(WeightChanger):
    def get_weight(self, prev_weight: int) -> int:
        return prev_weight - self.argument


@dataclass(slots=True)
class WeightDivider(WeightChanger):
    def get_weight(self, prev_weight: int) -> int | float:
        return prev_weight / self.argument


@dataclass(slots=True)
class WeightMultiplier(WeightChanger):
    def get_weight(self, prev_weight: int):
        return prev_weight * self.argument


@dataclass(slots=True)
class Slot:
    filters: list[Filter]
    ignore_global: bool


@dataclass(slots=True)
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
        if char in [r'\\', r'`']:
            continue

        if char == ' ' and not filter_chars:
            continue

        if char in filter_dict:
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


def process_filters(in_roles: set[PartialRole], filters: list[Filter]) -> set[PartialRole]:
    for filter_ in filters:
        in_roles = filter_.filter_roles(in_roles)

    return in_roles


def get_str_modifier(modifier_str: str, all_roles: set[PartialRole]) -> Modifier:
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
            raise SDGException(f'No roles for {roles_str}')

        return IndividualityModifier(roles)

    if modifier_name in ['limit', 'lim', 'rolelimit']:
        roles_str = arguments[1].strip()
        limit = int(arguments[2].strip()) if len(arguments) >= 3 else 1
        filters = get_str_filters(roles_str).filters
        roles = process_filters(all_roles, filters)

        if not roles:
            raise SDGException(f'No roles for {roles_str}')

        return LimitModifier(roles, limit)

    if modifier_name in ['exclusive', 'mutualexclusive', 'mutualexclusivity', 'mutexclusive', 'mexc', 'exc']:
        roles_str = arguments[1].strip()
        filters = get_str_filters(roles_str).filters
        roles = process_filters(all_roles, filters)

        second_roles_str = arguments[2].strip() if len(arguments) >= 3 else None
        second_roles = None
        if second_roles_str is not None:
            filters2 = get_str_filters(second_roles_str).filters
            second_roles = process_filters(all_roles, filters2)
            if not second_roles:
                raise SDGException(f'No roles for {second_roles_str}')

        if not roles:
            raise SDGException(f'No roles for {roles_str}')

        return MutualExclusiveModifier(roles, second_roles)

    raise SDGException(f'Invalid modifier: {modifier_str}')


def get_weight_chnager(in_str, all_roles: set[PartialRole]) -> WeightChanger:
    arguments = in_str.split(':')
    parameter = arguments[1].lower().strip()
    symbol = parameter[0]
    number = int(parameter[1:])
    limit = int(arguments[2].strip()) if len(arguments) >= 3 else None

    roles_str = arguments[0].lower().strip()
    filters = get_str_filters(roles_str).filters
    roles = process_filters(all_roles, filters)

    if not roles:
        raise SDGException(f'No roles for {roles_str} in ={in_str}')

    if symbol.isnumeric():
        return WeightSet(roles, int(parameter), limit)

    if symbol == '+':
        return WeightAdder(roles, number, limit)

    if symbol == '-':
        return WeightSubtractor(roles, number, limit)

    if symbol in ['*', 'x']:
        return WeightMultiplier(roles, number, limit)

    if symbol == '/':
        return WeightDivider(roles, number, limit)

    raise SDGException(f'Invalid weight changer: {in_str}')


def get_role_weight(role: PartialRole, weight_changers: list[WeightChanger]) -> int:
    valid_weights_changers = [w for w in weight_changers if w.check_role(role) and (w.limit is None or w.limit >= 1)]
    weight = 10

    for changer in valid_weights_changers:
        weight = changer.get_weight(weight)

    if weight <= 0:
        raise SDGException(f'Weight of {role.name} was resolved to {weight}, under or equal to 0')

    return weight


def get_all_weights(roles: list[PartialRole], weight_changers: list[WeightChanger]) -> list[int]:
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
    partial_roles = {PartialRole.from_role(r) for r in all_roles}

    for line in message_lines:
        if not line:
            continue
        line = line.strip(r'`\\')
        if line.startswith('+'):
            slot_str = line[1:]
            fake_slot = get_str_filters(slot_str)
            global_filters += fake_slot.filters
            continue
        if line.startswith('?'):
            modifier_str = line[1:]
            modifiers.append(get_str_modifier(modifier_str, partial_roles))
            continue
        if line.startswith('='):
            weight_str = line[1:]
            weights.append(get_weight_chnager(weight_str, partial_roles))
            continue

        slot = get_str_filters(line)
        slots.append(slot)

    return Rolelist(slots=slots, global_filters=global_filters, modifiers=modifiers, weight_changers=weights)


def generate_rolelist_roles(rolelist: Rolelist, full_roles: list[Role]) -> list[Role]:
    new_slots = []
    roles: list[PartialRole] = []
    weight_changers = rolelist.weight_changers
    partial_roles = {PartialRole.from_role(r) for r in full_roles}

    for slot in rolelist.slots:
        if not slot.ignore_global:
            slot.filters += rolelist.global_filters

        new_slots.append(slot)

    for slot in new_slots:
        valid_roles = partial_roles
        for r_filter in slot.filters:
            valid_roles = r_filter.filter_roles(valid_roles)

        for modifier in rolelist.modifiers:
            valid_roles = modifier.modify_valid_roles(valid_roles, roles)

        if not valid_roles:
            raise SDGException(f'No valid roles for {slot}')

        list_valid_roles = list(valid_roles)

        if not rolelist.weight_changers:
            roles.append(random.choice(list_valid_roles))
        else:
            weights = get_all_weights(list_valid_roles, weight_changers)
            role = random.choices(list_valid_roles, weights=weights, k=1)[0]

            for weight_changer in weight_changers:
                if weight_changer.limit and role in weight_changer.roles:
                    weight_changer.limit -= 1

            roles.append(role)

    refull_roles = [r.to_role(full_roles) for r in roles]

    return refull_roles
