import logging
import itertools
import time
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

class CacheEntry:
	def __init__(self, score, bias):
		self.score = score
		self.bias = bias

class Hand:
	def __init__(self, app, cards):
		self.cards = cards
		self.app = app

	def calc_score(self):
		hand_resources = []

		for numElements in range(1,5):
			tier_resources = []

			for elements in itertools.combinations_with_replacement(Element, numElements):
				boss = Boss(elements)

				max_resources = max(map(lambda h: boss.calculateResources(h), self.cards))
				tier_resources.append(max_resources)

			hand_resources.append(mean(tier_resources))

		return mean(hand_resources)

	def calc_bias(self):
		hand_bias = []

		for numElements in range(1,5):
			tier_bias = []

			for elements in itertools.combinations_with_replacement(Element, numElements):
				boss = Boss(elements)

				try:
					max_wood = max(map(lambda h: boss.calculateResources(h), filter(lambda c: c.resource == Resource.WOOD, self.cards)))
				except ValueError:
					max_wood = 0

				try:
					max_stone = max(map(lambda h: boss.calculateResources(h), filter(lambda c: c.resource == Resource.STONE, self.cards)))
				except ValueError:
					max_stone = 0

				#logging.info(max_wood)
				#logging.info(max_stone)

				bias = max_wood - max_stone

				logging.debug("Bias: {}".format(bias))

				tier_bias.append(bias)

			hand_bias.append(mean(tier_bias))

		return mean(hand_bias)

	def cache(self):
		self.app.hand_cache[repr(self.cards)] = CacheEntry(self.calc_score(), self.calc_bias())

	def get_score(self):
		if repr(self.cards) not in self.app.hand_cache:
			self.cache()

		return self.app.hand_cache[repr(self.cards)].score

	def get_bias(self):
		if repr(self.cards) not in self.app.hand_cache:
			self.cache()

		return self.app.hand_cache[repr(self.cards)].bias

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

	def get_score(self):
		if not hasattr(self, 'score'):
			logging.debug("Scoring {}...".format(self))

			deck_resources = []
			deck_bias = []

			for hand_cards in itertools.combinations(self.cards, 3):
				hand = Hand(self.app, hand_cards)
				deck_resources.append(hand.get_score())
				deck_bias.append(hand.get_bias())

			self.base_score = mean(deck_resources)
			self.bias = mean(deck_bias)
			self.score = self.base_score - abs(self.bias) / 2
			logging.debug("Deck base score: {}".format(self.base_score))
			logging.debug("Deck bias: {}".format(self.bias))
			logging.debug("Deck score: {}".format(self.score))

		return self.score

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

		return amount

class AppState:
	def __init__(self):
		self.hand_cache = {}

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

		current_score = self.deck.get_score()
		logging.info("Current score: {}".format(current_score))
		deck_options.append(self.deck)

		for deck_size in range(len(self.deck)-1, 9, -1):
			logging.info("Deck size: {}".format(deck_size))

			for cards in itertools.combinations(self.deck.cards, deck_size):
				deck = Deck(self, cards)
				new_score = deck.get_score()

				logging.debug(deck)
				logging.debug("New score: {}".format(new_score))

				deck_options.append(deck)

		deck_options.sort(key=lambda d: d.get_score(), reverse=True)

		for deck_option in deck_options[:10]:
			logging.info("Score: {:3f} | {}".format(deck_option.get_score(), deck_option))


		

#card = Card([Element.EARTH, Element.FIRE, Element.FIRE], Resource.WOOD, 1)
#boss = Boss([Element.FIRE])

#boss.calculateResources(card)

app = AppState()
app.load('input.txt')

start_time = time.time()

app.run()

logging.info("Execution time: {}".format(time.time() - start_time))