import logging
import itertools
import time
import math
import copy
import inspect
import random
import json
from statistics import mean
from enum import Enum
from functools import lru_cache
from functools import cached_property

import progressbar

import profile_tools
from profile_tools import profile_cumulative
from profile_tools import profile
from profile_tools import ChunkProfiler

progressbar.streams.wrap_stderr()
logging.basicConfig(level=logging.INFO)

class Element(Enum):
	#NONE = 0

	EARTH = 1
	E = 1

	FIRE = 2
	F = 2

	ICE = 3
	I = 3

	LIGHTNING = 4
	L = 4

	def __str__(self):
		return self.name.title()

	def __repr__(self):
		return "<e-{}>".format(self.name)

	def __lt__(self, o):
		return self.value < o.value

	def short(self):
		return self.name[:1]

class Resource(Enum):
	#NONE = 0

	WOOD = 1
	W = 1

	STONE = 2
	S = 2

	COPPER = 3
	C = 3

	def __str__(self):
		return self.name.title()

	def __repr__(self):
		return "<r-{}>".format(self.name)

	def short(self):
		return self.name[:1]

class ResourceContainer:
	def __init__(self, wood=0, stone=0):
		self.wood = wood
		self.stone = stone

	@classmethod
	def create(cls, amount, resource):
		if resource == Resource.WOOD:
			return cls(wood=amount)
		elif resource == Resource.STONE:
			return cls(stone=amount)
		else:
			raise Exception()

	def __repr__(self):
		return "<{:.3f} Wood, {:.3f} Stone>".format(self.wood, self.stone)

	def __add__(self, o):
		total_wood = self.wood + o.wood
		total_stone = self.stone + o.stone
		return ResourceContainer(wood=total_wood, stone=total_stone)

	def __sub__(self, o):
		total_wood = self.wood - o.wood
		total_stone = self.stone - o.stone
		return ResourceContainer(wood=total_wood, stone=total_stone)

	def __mul__(self, o):
		if isinstance(o, float):
			total_wood = self.wood * o
			total_stone = self.stone * o
			return ResourceContainer(wood=total_wood, stone=total_stone)

	def __div__(self, o):
		if isinstance(o, float):
			total_wood = self.wood / o
			total_stone = self.stone / o
			return ResourceContainer(wood=total_wood, stone=total_stone)

	def __lt__(self, o):
		return self.total() < o.total()

	def __gt__(self, o):
		return self.total() > o.total()

	def __le__(self, o):
		return self.total() <= o.total()

	def __ge__(self, o):
		return self.total() >= o.total()

	def total(self):
		return self.wood + self.stone

	def delta(self):
		return abs(self.wood - self.stone)

	def surplus(self):
		if self.wood > self.stone:
			return Resource.WOOD
		elif self.stone > self.wood:
			return Resource.STONE
		else:
			return None

	def scarce(self):
		if self.wood < self.stone:
			return Resource.WOOD
		elif self.stone < self.wood:
			return Resource.STONE
		else:
			return None

class Hand:
	damage_cache = {}

	def __init__(self, deck, cards):
		self.cards = cards
		self.deck = deck
		self.app = deck.app

		n = len(self.deck)
		r = len(self.cards)
		self.draw_chance = 1
		self.draw_chance /= math.factorial(n) / math.factorial(r) / math.factorial(n-r)

	def __repr__(self):
		return repr(self.cards)

	def get_score(self):
		if repr(self.cards) not in self.app.hand_cache:
			resources = ResourceContainer()

			for boss in self.app.bosses:
				max_resources = max(map(lambda c: boss.calculate_resources(c), self.cards))
				resources += max_resources * boss.get_spawn_chance()

			self.app.hand_cache[repr(self.cards)] = resources

		return self.app.hand_cache[repr(self.cards)] * self.draw_chance

	def get_flip_cost(self, boss):
		try:
			max_wood = max(map(lambda c: boss.calculate_resources(c), filter(lambda c: c.resource == Resource.WOOD, self.cards)))
		except ValueError:
			max_wood = ResourceContainer()

		try:
			max_stone = max(map(lambda c: boss.calculate_resources(c), filter(lambda c: c.resource == Resource.STONE, self.cards)))
		except ValueError:
			max_stone = ResourceContainer()

		if __debug__:
			logging.debug("Wood: ".format(max_wood))
			logging.debug("Stone: ".format(max_stone))

		flip_cost = abs(max_wood.total() - max_stone.total())

		if __debug__:
			logging.debug("{} vs {} flip cost: {}".format(self, boss, flip_cost))

		return flip_cost

	def get_damage(self):
		key = repr(self)

		if key not in self.damage_cache:
			damage = 0

			for boss in self.app.bosses:
				damage += max(map(lambda c: boss.calculate_damage(c), self.cards)) * boss.get_spawn_chance()

			self.damage_cache[key] = damage

		return self.damage_cache[key]

class BossHandPair():
	def __init__(self, cd, boss, hand):
		self.cdeck = cd
		self.boss = boss
		self.hand = hand
		self.app = cd.app

		self.set_default_selection()

		self.is_flippable = len(set(map(lambda c: c.resource, self.hand.cards))) > 1

	def __repr__(self):
		return "<BHP-({}, {})-<{}>>".format(self.boss, self.hand, self.selection)

	def select(self, card):
		self.selection = card
		self.recalculate()

	def set_default_selection(self):
		# sort the hand by value
		sorted_cards = sorted(self.hand.cards, key=lambda c: self.boss.calculate_resources(c), reverse=True)

		self.select(sorted_cards[0])

	def recalculate(self):
		if hasattr(self, 'resources'):
			self.cdeck.resources -= self.resources

		self.resources = self.boss.calculate_resources(self.selection) * self.boss.get_spawn_chance() * self.hand.draw_chance

		self.cdeck.resources += self.resources

	def get_resources(self):
		return self.resources

	def flip(self):
		if not self.is_flippable:
			raise Exception()

		filtered_cards = list(filter(lambda c: c.resource != self.selection.resource, self.hand.cards))
		sorted_cards = sorted(filtered_cards, key=lambda c: self.boss.calculate_resources(c), reverse=True)

		self.select(sorted_cards[0])

	def get_flip_cost(self):
		return self.hand.get_flip_cost(self.boss)

class ComplexDeck():
	def __init__(self, deck):
		self.deck = deck
		self.app = deck.app
		self.resources = ResourceContainer()
		self.invalids = []

		self.init_bh_pairs()

	def init_bh_pairs(self):
		# 1) calculate all combinations of bosses
		bosses = self.app.bosses

		# 2) calculate all possible hands for this deck
		hands = self.deck.get_hands()

		# 3) calculate all possible boss-hand pairs
		self.pairs = []

		for boss in bosses:
			for hand in hands:
				self.pairs.append(BossHandPair(self, boss, hand))

	def get_resources(self):
		return self.resources

	def dump_score_data(self):
		data = {}

		for pair in self.pairs:
			data[repr(pair.selection)] = repr(pair.resources)

		self.app.score_data[str(self.deck)] = data

class Deck:
	def __init__(self, app, cards):
		self.cards = cards
		self.app = app

	def __str__(self):
		if len(self) == len(self.app.deck):
			return "Existing"

		missing_cards = []

		for card in self.app.deck.cards:
			if card not in self.cards:
				missing_cards.append(card)

		return "Shatter {}".format(", ".join(map(lambda c: repr(c), missing_cards)))

	def __len__(self):
		return len(self.cards)

	def get_hands(self):
		if not hasattr(self, 'hands'):
			self.hands = []

			for hand_cards in itertools.combinations(self.cards, 3):
				self.hands.append(Hand(self, hand_cards))

		return self.hands

	def get_score(self):
		if not hasattr(self, 'score'):
			if __debug__:
				logging.debug("Scoring {}...".format(self))

			self.resources = ResourceContainer()

			for hand in self.get_hands():
				self.resources += hand.get_score()

			if __debug__:
				logging.debug("{} deck resources: {}".format(self, self.resources))

			self.base_score = self.resources.total()
			self.base_delta = self.resources.delta()
			#self.score = self.base_score - self.base_delta * 0.0842
			#self.score = self.base_score - 0.11424 * (self.base_delta / 1.36) ** 3.475
			self.score = self.base_score - 0.96 * self.base_delta ** 2 / self.base_score

			if __debug__:
				logging.debug("Deck score: {}".format(self.score))

		return self.score

	def get_damage(self):
		if not hasattr(self, 'damage'):
			self.damage = 0

			for hand in self.get_hands():
				self.damage += hand.get_damage() * hand.draw_chance

			self.damage *= self.get_collection_bonus()

		return self.damage

	def minimize_delta(self):
		if __debug__:
			logging.debug("Minimizing delta on {}...".format(self))

		# 1) create complex deck
		cd = ComplexDeck(self)

		# 2a) calculate the total wood and stone gained by the deck
		resources = cd.get_resources()

		# 2b) calculate the wood-stone delta
		best_delta = resources.delta()

		if best_delta == 0:
			self.resources = cd.get_resources()
			self.score = min(self.resources.wood, self.resources.stone) * 2
			return

		# 3) determine which resource we need to gain more of
		target_resource = resources.scarce()

		# 4) filter list of pairs to ones that can have their resource flipped favorably
		bh_pairs_f = list(filter(lambda bhp: bhp.is_flippable and bhp.get_resources().total() > 0 and bhp.get_resources().surplus() != target_resource, cd.pairs))

		# 5) sort list of boss-hand pairs by its opportunity cost of switching resources, desc
		bh_pairs_f.sort(key=lambda bhp: bhp.get_flip_cost())
			
		if __debug__:
			logging.debug("Start delta: {}".format(best_delta))

		# 6) one by one, flip the resource gain of each hand-boss pair until the wood-stone delta is minimized
		while bh_pairs_f:
			bhp = bh_pairs_f.pop(0)
			bhp.flip()

			if cd.get_resources().delta() < best_delta:
				best_delta = cd.get_resources().delta()
			else:
				bhp.flip()
				break 

		self.resources = cd.get_resources()
		self.score = min(self.resources.wood, self.resources.stone) * 2

		if self.app.dump_score_data:
			cd.dump_score_data()

	def get_collection_bonus(self):
		if not hasattr(self, 'collection_bonus'):
			self.collection_bonus = 1.00 + 0.01 * sum(list(map(lambda c: len(c.elements), self.cards)))

		return self.collection_bonus

	def add_card(self, card):
		self.cards.append(card)

		if hasattr(self, 'hands'):
			del self.hands
		if hasattr(self, 'score'):
			del self.score
		if hasattr(self, 'damage'):
			del self.damage
		if hasattr(self, 'collection_bonus'):
			del self.collection_bonus

class Card:
	def __init__(self, elements, resource, resource_amount):
		self.elements = tuple(sorted(elements))
		self.resource_amount = resource_amount
		self.resource = resource
		self.level = 1

	def __str__(self):
		return "Card-{}-{}{}".format("".join(map(lambda e: e.short(), self.elements)), self.resource.short(), self.resource_amount)

	def __repr__(self):
		return "<Card-{}-{}{}>".format("".join(map(lambda e: e.short(), self.elements)), self.resource.short(), self.resource_amount)

	@classmethod
	def random(cls, minE=1, maxE=4, minR=0, maxR=4):
		elements = random.choices(list(Element), k=random.randint(minE,maxE))
		resource = random.choice((Resource.WOOD, Resource.STONE))
		resource_amount = random.randint(minR, maxR)

		if __debug__:
			logging.debug(elements)
			logging.debug(resource)
			logging.debug(resource_amount)

		return cls(elements, resource, resource_amount)

	@cached_property
	def level_multipliers(self):
		m = []

		for lvl in range(0, 100):
			val = 0.984 + 0.0343 * lvl - 0.00064 * lvl ** 2 + 0.00000668 * lvl ** 3 - 0.0000000267 * lvl ** 4
			m.append(val)

		return m

	#@lru_cache(maxsize=128)
	def get_level_multiplier(self):
		return self.level_multipliers[self.level]

class Boss:
	base_damage = [0, 30, 40, 55, 75]

	def __init__(self, app, elements):
		self.app = app
		self.elements = tuple(sorted(elements))
		self.elements_set = set(elements)

		n = 4
		r = len(elements)
		self.spawn_weight = 1
		self.spawn_total = n ** r

	def __str__(self):
		return "Boss-{}".format("".join(map(lambda e: e.short(), self.elements)))

	def __repr__(self):
		return "<Boss-{}>".format("".join(map(lambda e: e.short(), self.elements)))

	@lru_cache(maxsize=None)
	def get_hit_multiplier(self, card_elements, boss_elements):
		# Perfect Hit: earned when a card is played with the exact matching quantity of and type of Elements to the Boss
		# Perfect =  x5
		if card_elements == boss_elements:
			return 5.00
		elif len(list(filter(lambda e: e not in card_elements, set(boss_elements)))) == 0:
			# Critical Hit: earned when all of the Boss Elements are matched but the card played has additional unmatched Elements
			# Critical =  x2.5
			if len(list(filter(lambda e: e not in boss_elements, set(card_elements)))) > 0:
				return 2.50
			# Special Hit: earned when a card is played that matches all of the Elements of the Boss but is not a perfect hit
			# Special =  x3.5
			else:
				return 3.50
		# Clean Hit: earned when all of the card Elements match to the Boss but the Boss has additional Elements unmatched
		# Clean =  x1.75
		elif len(list(filter(lambda e: e not in boss_elements, set(card_elements)))) == 0:
			return 1.75
		# Match Hit: earned when any number of card Elements match Boss Elements
		# Match =  x1.25
		elif len(list(filter(lambda e: e in boss_elements, set(card_elements)))) > 0:
			return 1.25
		# Base Hit: earned when there are no matching Elements
		# Base =  x1
		else:
			return 1.00

	def calculate_damage(self, card):
		damage = self.__calculate_damage__(card.elements, self.elements)

		damage *= card.get_level_multiplier()

		return damage

	@lru_cache(maxsize=4096)
	def __calculate_damage__(self, card_elements, boss_elements):
		damage = self.base_damage[len(card_elements)]

		damage *= self.get_hit_multiplier(card_elements, boss_elements)

		# rarity ??????

		return damage

	def get_spawn_chance(self):
		return self.spawn_weight / self.spawn_total / 4

	def calculate_resources(self, card):
		return self.__calculate_resources__(tuple(self.elements_set), card.elements, card.resource_amount, card.resource)

	@lru_cache(maxsize=16384)
	def __calculate_resources__(self, boss_elements, card_elements, card_resource_amount, card_resource):
		matches = len(list(filter(lambda e: e in boss_elements, card_elements)))
		total_amount = matches * card_resource_amount

		if __debug__:
			logging.debug("{} vs {} resource amount: {} {}".format(card_elements, boss_elements, total_amount, card_resource))

		return ResourceContainer.create(total_amount, card_resource)

	@classmethod
	def random(cls, app):
		elements = random.choices(list(Element), k=random.randint(1,4))

		return cls(app, elements)

class AppState:
	def __init__(self):
		self.hand_cache = {}

		self.dump_score_data = False
		self.use_random_deck = False
		self.score_data = {}

	@cached_property
	def bosses(self):
		logging.info("Creating boss combinations...")

		bosses = []

		for numElements in range(1, 5):
			tier_bosses = []

			for elements in itertools.product(Element, repeat=numElements):
				tier_bosses.append(Boss(self, list(elements)))

			if __debug__:
				logging.debug(tier_bosses)

			while tier_bosses:
				boss = tier_bosses.pop()

				filtered = list(filter(lambda b: sorted(b.elements) == sorted(boss.elements), tier_bosses))

				if __debug__:
					logging.debug("Adding {} weight to {}".format(len(filtered), boss))

				boss.spawn_weight += sum(list(map(lambda b: b.spawn_weight, filtered)))

				bosses.append(boss)

				for boss in filtered:
					tier_bosses.remove(boss)

		if __debug__:
			total_spawn_chance = sum(map(lambda b: b.get_spawn_chance(), bosses))

			logging.debug("Total spawn chance: {}".format(total_spawn_chance))

			assert abs(1.0 - total_spawn_chance) < 0.000001

			logging.debug(bosses)

		return bosses

	def load(self, path):
		cards = []

		if self.use_random_deck:
			for i in range(10):
				cards.append(Card.random())
		else:
			with open(path, 'r') as f:
				raw_cards = f.read()

				raw_cards = raw_cards.split('\n')

				for line in raw_cards:
					if __debug__:
						logging.debug("Parsing line: {}".format(line))

					fields = line.split('\t')

					elements = list(map(lambda e: Element[e], fields[0]))

					if __debug__:
						logging.debug("Elements: {}".format(elements))

					resource = Resource[fields[1][:1]]
					resource_amount = int(fields[1][1:2])

					if __debug__:
						logging.debug("Resource: {} {}".format(resource_amount, resource))

					cards.append(Card(elements, resource, resource_amount))

		self.deck = Deck(self, cards)

	evaluated = 0

	def combinations_recursive(self, source_deck, candidates):
		#logging.info("recursing {}".format(len(source_deck)-1))

		for cards in itertools.combinations(source_deck.cards, len(source_deck)-1):
			if frozenset(cards) in candidates:
				continue

			deck = Deck(source_deck.app, list(cards))

			candidates.add(frozenset(deck.cards))

			self.evaluated += 1

			if len(deck) > 10 and deck.get_damage() > source_deck.get_damage():
				#logging.info("{} {} vs {} {}".format(deck, deck.get_damage(), source_deck, source_deck.get_damage()))
				self.combinations_recursive(deck, candidates)


	def maximize_damage(self, true_scores=True):
		logging.info("Creating deck combinations...")
		cards_set = set()
		cards_set.add(frozenset(self.deck.cards))

		self.evaluated = 1
		self.combinations_recursive(self.deck, cards_set)

		logging.info("Evaluated {} deck options.".format(self.evaluated))

		logging.info("Constructing deck list...")

		cards_list = list(cards_set)
		deck_options = list(map(lambda cards: Deck(self, list(cards)), cards_list))

		logging.info("Sorting decks...")
		deck_options.sort(key=lambda d: d.get_damage(), reverse=True)

		if true_scores:
			logging.info("Minimizing deltas..")

			for deck in progressbar.progressbar(deck_options[:5]):
				deck.minimize_delta()

		for deck in deck_options[:5]:
			deck.get_damage()
			deck.get_score()

		print("============================ Damage Rankings =========================================================")
		print("RNK\tDMG\tSCORE\tRESOURCES                    \tDESCRIPTION")
		print("======================================================================================================")
		for deck in deck_options[:5]:
			print("#{}\t{:.1f}\t{:.3f}\t{}\t{}".format(deck_options.index(deck)+1, deck.get_damage(), deck.get_score(), deck.resources, deck))

		self.deck = deck_options[0]

	def maximize_resources(self):
		deck_options = []

		for deck_size in range(len(self.deck), 9, -1):
			#logging.info("Deck size: {}".format(deck_size))

			for cards in itertools.combinations(self.deck.cards, deck_size):
				deck = Deck(self, list(cards))
				new_score = deck.get_score()

				if __debug__:
					logging.debug(deck)
					logging.debug("New score: {}".format(new_score))

				deck_options.append(deck)

		deck_options.sort(key=lambda d: d.get_score(), reverse=True)

		highest_score = 0
		true_decks = []

		for i in progressbar.progressbar(range(len(deck_options))):
			deck = deck_options[i]

			if deck.resources.total() < highest_score:
				continue

			deck.minimize_delta()
			true_decks.append(deck)

			if deck.get_score() > highest_score:
				highest_score = deck.get_score()

		true_decks.sort(key=lambda d: d.get_score(), reverse=True)

		print("================================== Trues Scores ===========================================================")
		print("RNK\tR2\tSCORE\tRESOURCES                     \tDESCRIPTION")
		print("===========================================================================================================")

		for deck in true_decks[:10]:
			print("#{}\t#{}\t{:.3f}\t{}\t{}".format(true_decks.index(deck)+1, deck_options.index(deck)+1, deck.get_score(), deck.resources, deck))

		if self.dump_score_data:
			with open('scores.json', 'w') as f:
				json.dump(self.score_data, f, indent=4, sort_keys=True)

			logging.info("Dumped score data to scores.json.")

		self.deck = true_decks[0]

	def run(self):
		for draws in range(999999):
			logging.info("Round {}".format(draws+1))
			drew = []

			# draw 3 cards
			for i in range(3):
				#card = Card.random(minE=4, minR=4)
				card = Card.random(minE=2)

				drew.append(card)
				self.deck.add_card(card)

			logging.info("Drew cards: {}".format(drew))

			self.maximize_damage(true_scores=False)

			logging.info("Current deck: {}".format(self.deck.cards))

		#self.maximize_damage()




app = AppState()
app.load('input.txt')

start_time = time.time()

app.run()

logging.info("Execution time: {:.3f}s".format(time.time() - start_time))
profile_tools.log_digest()