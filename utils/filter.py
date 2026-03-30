from __future__ import annotations

import random
import copy
import re

from dataclasses import dataclass
from abc import ABC, abstractmethod

from utils.classes import Role, Subalignment, Faction, SDGException


__all__ = [
    'generate_rolelist_roles',
    'get_rolelist',
    'get_flex_faction'
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


@dataclass(frozen=True)
class FactionedPartialRole:
    role: PartialRole
    flex_faction: None | str | Role | Subalignment | Faction = None


@dataclass(slots=True)
class FactionedRole:
    role: Role
    flex_faction: None | str | Role | Subalignment | Faction = None

    @property
    def faction_name(self) -> str | None:
        if self.flex_faction is None:
            return None

        if isinstance(self.flex_faction, str):
            return self.flex_faction

        return self.flex_faction.name

    @property
    def name(self) -> str:
        return self.role.name

    @property
    def id(self) -> int:
        return self.role.id

    def __post_init__(self):
        if self.is_role_in_flex_faction():
            self.flex_faction = None

    def is_role_in_flex_faction(self) -> bool:
        if self.flex_faction is None:
            return True

        if isinstance(self.flex_faction, str):
            return False

        if isinstance(self.flex_faction, Role):
            return self.role.id == self.flex_faction.id

        if isinstance(self.flex_faction, Subalignment):
            return self.role.subalignment.id == self.flex_faction.id

        if isinstance(self.flex_faction, Faction):
            return self.role.faction.id == self.flex_faction.id

        return False 

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
    weight: int | float = 10
    flex_faction: None | str | Role | Subalignment | Faction = None


@dataclass(slots=True)
class MultiSlot:
    slots: list[Slot]

    def get_slot_weights(self) -> list[int | float]:
        return [s.weight for s in self.slots]

    def pop_random_weighted_slot(self) -> Slot | None:
        if not self.slots:
            return None

        slot = random.choices(self.slots, weights=self.get_slot_weights(), k=1)[0]
        self.slots.remove(slot)

        return slot
        

@dataclass(slots=True)
class Rolelist:
    slots: list[Slot | MultiSlot]
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

def get_flex_faction(text: str, guild_info: GuildInfo) -> str | Role | Subalignment | Faction:
    fac_matches = [f for f in guild_info.factions if f.name.lower() == text.lower()]
    faction = None

    if fac_matches:
        faction = fac_matches[0]

    if not faction:
        sub_matches = [s for s in guild_info.subalignments if s.name.lower() == text.lower()]
        if sub_matches:
            faction = sub_matches[0]

    if not faction:
        role_matches = [r for r in guild_info.roles if r.name.lower() == text.lower()]
        if role_matches:
            faction = role_matches[0]

    if not faction:
        faction = text

    return faction

def get_slots_from_line(line: str, guild_info: GuildInfo) -> Slot | MultiSlot:
    split_strs = line.split('-')
    slots = []
    for s_s in split_strs:
        res = re.findall(r'\((.*?)\)', s_s)
        faction = None
        if res:
            res = res[0]
            fres = f'({res})'
            s_s = s_s.replace(fres, '').strip(' ')
            faction = get_flex_faction(res, guild_info)

        slot = get_str_filters(s_s)
        slot.flex_faction = faction
        slots.append(slot)

    if not slots:
        raise SDGException(f'Unable to get slots from {line}')

    if len(slots) == 1:
        return slots[0]

    return MultiSlot(slots)


def get_rolelist(message_str: str, guild_info: GuildInfo) -> Rolelist:
    all_roles = guild_info.roles
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

        slot = get_slots_from_line(line, guild_info)
        slots.append(slot)

    return Rolelist(slots=slots, global_filters=global_filters, modifiers=modifiers, weight_changers=weights)


def generate_rolelist_roles(rolelist: Rolelist, full_roles: list[Role]) -> list[FactionedRole]:
    roles: list[FactionedRole] = []
    p_roles: list[PartialRole] = []
    weight_changers = rolelist.weight_changers
    partial_roles = {PartialRole.from_role(r) for r in full_roles}

    slots_copy = copy.deepcopy(rolelist.slots)

    for u_slot in slots_copy:
        if isinstance(u_slot, MultiSlot):
            slot = u_slot.pop_random_weighted_slot()
        else:
            slot = u_slot

        if not slot.ignore_global:
            slot.filters += rolelist.global_filters

        valid_roles = []
        while not valid_roles:
            valid_roles = partial_roles
            for r_filter in slot.filters:
                valid_roles = r_filter.filter_roles(valid_roles)

            for modifier in rolelist.modifiers:
                valid_roles = modifier.modify_valid_roles(valid_roles, p_roles)

            if not valid_roles:
                if isinstance(u_slot, MultiSlot):
                    slot = u_slot.pop_random_weighted_slot()
                    if not slot.ignore_global:
                        slot.filters += rolelist.global_filters

                if isinstance(u_slot, Slot) or slot is None:
                    raise SDGException(f'No valid roles for {u_slot}')

        list_valid_roles = list(valid_roles)

        if not rolelist.weight_changers:
            role = random.choice(list_valid_roles)
            fp_role = FactionedPartialRole(role, slot.flex_faction)
        else:
            weights = get_all_weights(list_valid_roles, weight_changers)
            role = random.choices(list_valid_roles, weights=weights, k=1)[0]
            fp_role = FactionedPartialRole(role, slot.flex_faction)

            for weight_changer in weight_changers:
                if weight_changer.limit and role in weight_changer.roles:
                    weight_changer.limit -= 1

        roles.append(fp_role)
        p_roles.append(fp_role.role)

    refull_roles = [FactionedRole(r.role.to_role(full_roles), r.flex_faction) for r in roles]

    return refull_roles
