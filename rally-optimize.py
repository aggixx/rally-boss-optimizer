import logging
import itertools
import time
import math
from statistics import mean
from enum import Enum

logging.basicConfig(level=logging.INFO)

class Element(Enum):
	#NONE = 0

	EARTH = 1
	E = 1

	FIRE = 2
	F = 2

	LIGHTNING = 3
	L = 3

	ICE = 4
	I = 4

	def __str__(self):
		return self.name.title()

	def __repr__(self):
		return "<e-{}>".format(self.name)

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
		'''
		if isinstance(o, ResourceContainer):
			total_wood = self.wood * o.wood
			total_stone = self.stone * o.stone
			return ResourceContainer(wood=total_wood, stone=total_stone)
		'''
		if isinstance(o, float):
			total_wood = self.wood * o
			total_stone = self.stone * o
			return ResourceContainer(wood=total_wood, stone=total_stone)

	def __div__(self, o):
		'''
		if isinstance(o, ResourceContainer):
			total_wood = self.wood / o.wood
			total_stone = self.stone / o.stone
			return ResourceContainer(wood=total_wood, stone=total_stone)
		'''
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

class Hand:
	def __init__(self, deck, cards):
		self.cards = cards
		self.deck = deck
		self.app = deck.app

		n = len(self.deck)
		r = len(self.cards)
		self.draw_chance = 1
		self.draw_chance /= math.factorial(n) / math.factorial(r) / math.factorial(n-r)

	def calc_score(self):
		resources = ResourceContainer()

		for boss in self.app.get_bosses():
			max_resources = max(map(lambda h: boss.calculateResources(h), self.cards))
			resources += max_resources * boss.spawn_chance

		return resources

	def cache(self):
		self.app.hand_cache[repr(self.cards)] = self.calc_score()

	def get_score(self):
		if repr(self.cards) not in self.app.hand_cache:
			self.cache()

		return self.app.hand_cache[repr(self.cards)] * self.draw_chance

	def get_flip_cost(self, boss):
		try:
			max_wood = max(map(lambda h: boss.calculateResources(h), filter(lambda c: c.resource == Resource.WOOD, self.cards))).total()
		except ValueError:
			max_wood = ResourceContainer()

		try:
			max_stone = max(map(lambda h: boss.calculateResources(h), filter(lambda c: c.resource == Resource.STONE, self.cards))).total()
		except ValueError:
			max_stone = ResourceContainer()

		#logging.info(max_wood)
		#logging.info(max_stone)

		cost = abs(max_wood.total() - max_stone.total())
		logging.debug("{} vs {} flip cost: {}".format(self, boss, cost))

		return cost

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
			logging.debug("Scoring {}...".format(self))

			self.resources = ResourceContainer()

			for hand in self.get_hands():
				self.resources += hand.get_score()

			logging.debug("{} deck resources: {}".format(self, self.resources))

			self.score = self.resources.total() - self.resources.delta() / 2
			logging.debug("Deck score: {}".format(self.score))

		return self.score

	def get_biased_score(self):
		# 1) calculate all combinations of bosses
		bosses = self.app.get_bosses()

		# 2) calculate all possible hands for this deck
		hands = self.get_hands()

		# 3) calculate all possible boss-hand pairs
		bh_pairs = []
		for boss in bosses:
			for hand in hands:
				bh_pairs.append((boss, hand))

		# 4a) calculate the total wood and stone gained by the deck

		# 4b) calculate the wood-stone delta

		# 5a) filter list of pairs to ones that can have their resource flipped favorably

		# 5b) sort list of boss-hand pairs by its opportunity cost of switching resources, desc

		# 6) one by one, flip the resource gain of each hand-boss pair until the wood-stone delta is minimized

		pass

class Card:
	def __init__(self, elements, resource, resource_amount):
		self.elements = elements
		self.resource_amount = resource_amount
		self.resource = resource

	def __str__(self):
		return "Card-{}-{}{}".format("".join(map(lambda e: e.short(), self.elements)), self.resource.short(), self.resource_amount)

	def __repr__(self):
		return "<Card-{}-{}{}>".format("".join(map(lambda e: e.short(), self.elements)), self.resource.short(), self.resource_amount)

class Boss:
	def __init__(self, elements):
		self.elements = elements

		n = 4
		r = len(elements)
		self.spawn_chance = 1
		self.spawn_chance /= 4
		self.spawn_chance /= math.factorial(n+r-1) / math.factorial(r) / math.factorial(n-1)
		logging.debug("{} spawn chance: {}".format(self, self.spawn_chance))

	def __str__(self):
		return "Boss-{}".format("".join(map(lambda e: e.short(), self.elements)))

	def __str__(self):
		return "<Boss-{}>".format("".join(map(lambda e: e.short(), self.elements)))

	def calculateDamage(self, card):
		pass

	def calculateResources(self, card):
		logging.debug("Calculating resource gain for {} vs {}...".format(card, self))

		logging.debug("{} elements: {}".format(card, card.elements))
		logging.debug("{} elements: {}".format(self, self.elements))

		matching = list(filter(lambda e: e in self.elements, card.elements))

		logging.debug("Matching elements: {}".format(matching))

		amount = len(matching) * card.resource_amount

		logging.debug("Resource amount: {} {}".format(amount, card.resource))

		return ResourceContainer.create(amount, card.resource)

class AppState:
	def __init__(self):
		self.hand_cache = {}

	def get_bosses(self):
		if not hasattr(self, 'bosses'):
			logging.info("Creating boss combinations...")

			self.bosses = []

			for numElements in range(1, 5):
				for elements in itertools.combinations_with_replacement(Element, numElements):
					self.bosses.append(Boss(elements))

			#total_spawn_chance = sum(map(lambda b: b.spawn_chance, self.bosses))
			#logging.info("Total spawn chance: {}".format(total_spawn_chance))

		return self.bosses

	def load(self, path):
		cards = []

		with open(path, 'r') as f:
			raw_cards = f.read()

			raw_cards = raw_cards.split('\n')

			for line in raw_cards:
				logging.debug("Parsing line: {}".format(line))

				fields = line.split('\t')

				elements = list(map(lambda e: Element[e], fields[0]))
				logging.debug("Elements: {}".format(elements))

				resource = Resource[fields[1][:1]]
				resource_amount = int(fields[1][1:2])
				logging.debug("Resource: {} {}".format(resource_amount, resource))

				cards.append(Card(elements, resource, resource_amount))

		self.deck = Deck(self, cards)

	def run(self):
		deck_options = []

		'''
		current_score = self.deck.get_score()
		logging.info("Current score: {}".format(current_score))
		deck_options.append(self.deck)
		'''

		for deck_size in range(len(self.deck), 9, -1):
			logging.info("Deck size: {}".format(deck_size))

			for cards in itertools.combinations(self.deck.cards, deck_size):
				deck = Deck(self, cards)
				new_score = deck.get_score()

				logging.debug(deck)
				logging.debug("New score: {}".format(new_score))

				deck_options.append(deck)

		deck_options.sort(key=lambda d: d.get_score(), reverse=True)

		for deck_option in deck_options[:10]:
			logging.info("Score: {:.3f} | {} | {}".format(deck_option.get_score(), deck_option.resources, deck_option))


		

#card = Card([Element.EARTH, Element.FIRE, Element.FIRE], Resource.WOOD, 1)
#boss = Boss([Element.FIRE])

#boss.calculateResources(card)

app = AppState()
app.load('input.txt')

start_time = time.time()

app.run()

logging.info("Execution time: {}".format(time.time() - start_time))