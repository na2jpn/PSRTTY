"""0..100 TX control: quadratic low end, linear above 50; unchanged gain on open."""
import math

def level_to_gain(level):
    x=max(0,min(100,float(level)))
    return .00012*x*x if x <= 50 else .3 + .012*(x-50)

def gain_to_level(gain):
    x=max(0,min(.9,float(gain)))
    return round(math.sqrt(x/.00012) if x <= .3 else 50+(x-.3)/.012)
