#!/usr/bin/env python3
# The USTSA Points Calculations Script
# Author: Jack Rosenthal - 2015
import csv
import json
import sys
from datetime import datetime
from decimal import *
from enum import Enum

try:
    year = int(sys.argv[1])
except:
    try:
        year = int(input("Year [{}]: ".format(datetime.now().year)))
    except:
        year = datetime.now().year

racers = list()
csv.register_dialect('this', quoting=csv.QUOTE_NONE)
getcontext().prec = 64

class RaceType(Enum):
    GS = 0
    SC = 1
    CL = 2
    @property
    def ffactor(self):
        if self is RaceType.GS:
            return Decimal("660.0")
        if self is RaceType.SC or self is RaceType.CL:
            return Decimal("500.0")
        return Decimal("500.0")
    @property
    def fullname(self):
        if self is RaceType.GS:
            return "Giant Slalom"
        if self is RaceType.SC:
            return "Sprint Classic"
        if self is RaceType.CL:
            return "Classic"
        return self.name
    @property
    def zerofactor(self):
        return zeroes[self]

zeroes = {this: this.ffactor for this in RaceType}

# Populate prevseason dictionary from last year
prevseason = dict()
with open("points{}.json".format(year - 1), 'r') as f:
    prevseason = json.load(f)
for rkey, rval in prevseason.items():
    prevseason[rkey] = {RaceType[key]: Decimal(str(val)) for key, val in prevseason[rkey].items()}
    for rtype in RaceType:
        if rtype not in prevseason[rkey] or prevseason[rkey][rtype] > rtype.ffactor:
            prevseason[rkey][rtype] = rtype.ffactor
lszeroes = prevseason["data-zeroes"]

class Gender(Enum):
    M = 0
    F = 1
    @property
    def glongname(self):
        if self is Gender.M:
            return 'Mens'
        if self is Gender.F:
            return 'Ladies'
    @property
    def ilongname(self):
        if self is Gender.M:
            return 'Male'
        if self is Gender.F:
            return 'Female'
    @property
    def shortname(self):
        if self is Gender.M:
            return 'M'
        if self is Gender.F:
            return 'L'

class Racer:
    def __init__(self, name, results, gender, inj):
        self.name = name
        self.results = results
        self.gender = gender
        self.inj = inj
    @property
    def season_avg(self):
        return sum([self.best_avg(this) for this in RaceType])/len(RaceType)
    @property
    def ls(self):
        if self.name in prevseason:
            return prevseason[self.name]
        return {this: this.ffactor for this in RaceType}
    def best_two(self, racetype):
        templist = list()
        for i in range(len(self.results)):
            if self.results[i].time != None and self.results[i].race.rtype == racetype:
                templist.append(self.results[i].points)
        for i in range(2):
            templist.append(self.last_penalized(racetype))
        templist.sort()
        return templist[:2]
    def best_avg(self, racetype):
        templist = self.best_two(racetype)
        avg = (templist[0] + templist[1]) / 2
        if avg < racetype.zerofactor:
            zeroes[racetype] = avg
        return avg - zeroes[racetype]
    def last_penalized(self, racetype):
        if self.inj:
            return min(Decimal('1.22') * self.ls[racetype] + Decimal('0.22') * lszeroes[racetype], racetype.ffactor)
        else:
            return min(Decimal('1.44') * self.ls[racetype] + Decimal('0.44') * lszeroes[racetype], racetype.ffactor)

class Result:
    DNF = "DNF"
    DNS = "DNS"
    DSQ = "DSQ"
    FIN = "FIN"
    def __init__(self, time=None, raceid=None, result=None):
        if time is not Result.DNF and time is not Result.DNS and time is not Result.DSQ:
            self._time = time
            self.result = Result.FIN if result is None else Result.resultitem(result)
        else:
            self._time = None
            self.result = time if result is None else Result.resultitem(result)
        self.race = races[raceid]
    @property
    def finished(self):
        if self.result is Result.DNF or self.result is Result.DNS or self.result is Result.DSQ or self._time is None:
            return False
        return True
    @property
    def started(self):
        if self.result is Result.DNS or (self._time is None and self.result is not Result.DNF and self.result is not Result.DSQ):
            return False
        return True
    @property
    def time(self):
        if self.finished:
            return self._time
        return None
    @property
    def points(self):
        if self.time != None:
            return self.raw_points + self.race.penalty
        return None
    @property
    def raw_points(self):
        if self.time != None:
            return (self.time/self.race.best_time - 1) * self.race.rtype.ffactor
        return None
    @property
    def place(self):
        if not self.finished:
            return None
        my_place = 1
        for k in range(len(racers)):
            for j in range(len(racers[k].results)):
                if racers[k].results[j].race is self.race and racers[k].results[j].finished and racers[k].results[j].time < self.time:
                    my_place += 1
        return my_place

    @staticmethod
    def resultitem(item):
        if item == "DNF":
            return Result.DNF
        if item == "DNS":
            return Result.DNS
        if item == "DSQ":
            return Result.DSQ
        return item

class Race:
    def __init__(self, rtype, name, penalty=None):
        self.rtype = rtype
        self.name = name
        self._sto_penalty = penalty
        self._sto_B = None
        self._sto_C = None
        self.stored_best = None
    @property
    def best_time(self):
        if self.stored_best != None:
            return self.stored_best
        self.stored_best = Decimal("inf")
        for k in range(len(racers)):
            for j in range(len(racers[k].results)):
                if racers[k].results[j].race is self and racers[k].results[j].time is not None and racers[k].results[j].time < self.stored_best:
                    self.stored_best = racers[k].results[j].time
        return self.stored_best
    @property
    def penalty(self):
        if self._sto_penalty is not None:
            return self._sto_penalty
        # (A + B - C)/10 = Race Penalty
        self._sto_penalty = (self.A + self.B - self.C)/10
        return self._sto_penalty
    @property
    def A(self):
        # A is the sum of the five best last year's points in the RaceType
        #  of those who started the race
        points_start = []
        for k in range(len(racers)):
            for j in range(len(racers[k].results)):
                if racers[k].results[j].race is self and racers[k].results[j].started:
                    points_start.append(racers[k].ls[self.rtype])
        points_start.sort()
        return sum(points_start[:5])
    @property
    def BC(self):
        # B is the sum of the five best last year's points in the RaceType
        #  of those who finished the race in the top ten
        # C is the sum of the unpenalized race points of B's racers results
        tt_finish = list()
        for k in range(len(racers)):
            for j in range(len(racers[k].results)):
                if racers[k].results[j].race is self and racers[k].results[j].finished and racers[k].results[j].place <= 10:
                    tt_finish.append(racers[k])
        points_finish = list()
        for k in range(len(tt_finish)):
            for j in range(len(tt_finish[k].results)):
                if tt_finish[k].results[j].race is self:
                    points_finish.append([tt_finish[k].ls[self.rtype], tt_finish[k].results[j]])
        points_finish = sorted(points_finish, key=lambda l:l[0])
        points_finish = points_finish[:5]
        B = Decimal('0')
        C = Decimal('0')
        for k in range(len(points_finish)):
            B += points_finish[k][0]
            C += points_finish[k][1].raw_points
        return (B, C)
    @property
    def B(self):
        if self._sto_B is None:
            (self._sto_B, self._sto_C) = self.BC
        return self._sto_B
    @property
    def C(self):
        if self._sto_C is None:
            (self._sto_B, self._sto_C) = self.BC
        return self._sto_C


#races = [Race(RaceType.GS, "Howelsen Hill 1", 37.439),
#         Race(RaceType.GS, "Howelsen Hill 2", 32.369),
#         Race(RaceType.SC, "Vail", 25.762),
#         Race(RaceType.SC, "Kare Anderson", 69.072),
#         Race(RaceType.SC, "Nationals 1", -6.348),
#         Race(RaceType.SC, "Nationals 2", 4.396),
#         Race(RaceType.SC, "Short Sprint", -3.324),
#         Race(RaceType.CL, "Nationals 1", -1.932),
#         Race(RaceType.CL, "Nationals 2", 2.87),
#         Race(RaceType.SC, "WSC", -9.2741),
#         Race(RaceType.CL, "WSC", -1.503),
#         Race(RaceType.SC, "WJC", 61.076),
#         Race(RaceType.CL, "WJC", 55.612)]

races = list()

def timeeval(time):
    if time == '':
        return None
    try:
        return Decimal(time)
    except InvalidOperation:
        if ':' in time:
            #Evaluate minutes and seconds
            minutes, _s, seconds = time.partition(':')
            return Decimal('60') * Decimal(minutes) + Decimal(seconds)
        elif time == "DNF":
            return Result.DNF
        elif time == "DNS":
            return Result.DNS
        elif time == "DSQ":
            return Result.DSQ
        else: raise ValueError

with open('results{}.csv'.format(year), newline='') as f:
    reader = csv.reader(f, 'this')
    j = 0
    for row in reader:
        if j == 0:
            i = 0
            for item in row:
                if i > 1:
                    field = item.split("#")
                    try:
                        races.append(Race(RaceType[field[1]], field[0], penalty=field[2]))
                    except:
                        races.append(Race(RaceType[field[1]], field[0]))
                i += 1
        else:
            i = 0
            raceresults = list()
            for item in row:
                if i == 0:
                    thisname = item
                elif i == 1:
                    if item == 'inj':
                        inj = True
                    else:
                        inj = False
                else:
                    raceresults.append(Result(timeeval(item),i-2))
                i += 1
            thisname, _s, gender = thisname.partition("#")
            racers.append(Racer(thisname, raceresults, Gender.M if gender is 'M' else Gender.F, inj))
        j += 1

for k in range(len(racers)):
    racers[k].season_avg # Calculate zeroes first for proper sorting

racers = sorted(racers, key=lambda l:l.season_avg)

# Create seasonfile for next year
seasonobj = dict()
for k in range(len(racers)):
    seasonobj[racers[k].name] = {this.name: str(racers[k].best_avg(this)) for this in RaceType}
seasonobj["data-zeroes"] = {this.name: str(this.zerofactor) for this in RaceType}
with open("points{}.json".format(year), 'w') as f:
    json.dump(seasonobj, f, indent=4)
del seasonobj

# Output LaTeX results file

def seasontable(gender):
    out = "\\begin{tabular}{l" + ''.join(' c' for _x in RaceType) + " c}\n"
    out += "\\textbf{" + gender.glongname + "\' Points}" + ''.join(" & %s" % (racetype.name) for racetype in RaceType) + " & Average\\\\\n\\hline\n"
    for k in range(len(racers)):
        if racers[k].gender == gender:
            out += racers[k].name + ("$\\dagger$" if racers[k].inj else "") + ''.join(" & %.2f" % (racers[k].best_avg(racetype)) for racetype in RaceType) + " & %.2f \\\\\n" % (racers[k].season_avg)
    out += "\\end{tabular}\n\n"
    return out

with open("output.tex", 'w') as tp:
    tp.write("\\batchmode\n")
    tp.write("\\documentclass{article}\n")
    tp.write("\\usepackage[landscape,margin=2cm]{geometry}\n")
    tp.write("\\usepackage{adjustbox}\n")
    tp.write("\\usepackage{longtable}\n")
    tp.write("\\begin{document}\n")
    tp.write("\\centering\n")
    tp.write("{\\bfseries \\sffamily \\huge United States Telemark Ski Association \par}\n")
    tp.write("{\\sffamily \\LARGE %d National Points List \par}\n" % (year))
    tp.write("\\vspace{10 pt}\\hfill\n")
    tp.write("\\adjustbox{valign=t}{\\begin{minipage}{0.49\\textwidth}\n")
    tp.write("\\centering\n")
    tp.write(seasontable(Gender.F))
    tp.write("\\begin{center}\n")
    tp.write("\\textbf{Zero Factors}\n\n")
    for racetype in RaceType:
        tp.write("%s: %.2f\n\n" % (racetype.name, racetype.zerofactor))
    tp.write("\\end{center}\n")
    tp.write("\\begin{flushleft}\n")
    tp.write("{\small A dagger ($\\dagger$) next to a racer\'s name indicates the racer was injured for the season and was given only a 22\\% penalty on the last season rather than 44\\%.\\par}\n")
    tp.write("\\end{flushleft}\n")
    tp.write("\\end{minipage}}\n")
    tp.write("\\adjustbox{valign=t}{\\begin{minipage}{0.49\\textwidth}\n")
    tp.write("\\centering\n")
    tp.write(seasontable(Gender.M))
    tp.write("\\end{minipage}}\n")
    for racetype in RaceType:
        racers = sorted(racers, key=lambda l:l.best_avg(racetype)) # Sort racers by our race type
        tp.write("\\clearpage\n")
        tp.write("{\\sffamily \\bfseries \\LARGE %s Points Detail \par}\n" % (racetype.fullname))
        tp.write("Race points for the %s category are listed below. The two best points for each racer are in \\textbf{bold}. The last season's penalized points may be used twice." % (racetype.name) +
                 " A dagger ($\\dagger$) next to a racer\'s name indicates the racer was injured for the season and was given only a 22\\% penalty on the last season rather than 44\\%.")
        tp.write("\\begin{longtable}{l c" + ''.join((' c' if races[k].rtype is racetype else '') for k in range(len(races))) + "}\n")
        tp.write("Racer\'s Name & Last Season (penalized)" + ''.join((" & %s" % (races[k].name) if races[k].rtype is racetype else '') for k in range(len(races))) + " \\\\\n\\hline\n")
        tp.write("\\endfirsthead\n")
        i = 2
        for k in range(len(races)): # Calculate columns for multicolumn
            if races[k].rtype is racetype: i += 1
        tp.write("\\multicolumn{%d}{c}{\\emph{Continued from previous page}}\\\\ \\\\\n" % (i))
        tp.write("Racer\'s Name & Last Season (penalized)" + ''.join((" & %s" % (races[k].name) if races[k].rtype is racetype else '') for k in range(len(races))) + " \\\\\n\\hline\n")
        tp.write("\\endhead\n")
        tp.write("Race Penalties $\\longrightarrow$ &" + ''.join((" & %.2f" % (races[k].penalty) if races[k].rtype is racetype else '') for k in range(len(races))) + " \\\\\n\\hline\n")
        for k in range(len(racers)):
            tp.write(racers[k].name + ("$\\dagger$" if racers[k].inj else "") + " & " + ("\\textbf{%.2f}" if racers[k].last_penalized(racetype) in racers[k].best_two(racetype) else "%.2f") % (racers[k].last_penalized(racetype)))
            for j in range(len(races)):
                if (races[j].rtype is racetype):
                    if racers[k].results[j].points is not None:
                        tp.write(" & " + ("\\textbf{%.2f}" if racers[k].results[j].points in racers[k].best_two(racetype) else "%.2f") % (racers[k].results[j].points))
                    else:
                        tp.write(" & ---")
            tp.write(" \\\\\n")
        tp.write("\\end{longtable}\n")
    tp.write("\\end{document}\n")

import os
os.system("pdflatex output")
